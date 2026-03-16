"""
BillShield — Auditor Agent (the star agent)

Model: Nemotron Super 120B (reasoning ON)
Tools: None (pre-fetches rules from Supabase, then reasons over them)
Purpose: Detect billing errors — duplicates, upcoding, unbundling, overcharges.

Data source: Real CMS NCCI quarterly PTP edits + MUE limits + heuristic rules,
all stored in Supabase billing_rules table and queried by CPT code using
JSONB containment so only relevant rules enter the context window.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .state import BillShieldState
from ._common import (
    extract_json,
    get_super_llm,
    load_prompt,
    rate_limit_wait,
)
from tools import db


def _load_relevant_billing_rules(charges: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Fetch billing rules relevant to the CPT codes in this bill from Supabase.

    Uses JSONB containment queries on billing_rules.trigger_codes so that
    only rules matching the bill's specific CPT codes are returned.
    For a typical 5-7 line bill this returns ~10-30 rules instead of 48K+.
    """
    cpt_codes = [
        str(c.get("cpt_code", "")).strip()
        for c in charges
        if c.get("cpt_code")
    ]
    cpt_codes = [c for c in cpt_codes if c]

    if not cpt_codes:
        return {}

    try:
        return db.get_rules_for_bill(cpt_codes)
    except Exception as exc:
        return {"_error": f"Failed to fetch billing rules from Supabase: {exc}"}


def run_auditor(state: BillShieldState) -> dict[str, Any]:
    """Auditor node: analyzes charges for billing errors using reasoning."""
    charges = state.get("parsed_charges", [])
    icd_codes = state.get("icd_codes", [])
    pricing = state.get("pricing_results", [])

    if not charges:
        return {
            "errors_found": [],
            "error_count": 0,
            "current_agent": "auditor",
        }

    billing_rules = _load_relevant_billing_rules(charges)
    rule_summary = _build_rule_summary(billing_rules)

    llm = get_super_llm(max_completion_tokens=8192)
    system_prompt = load_prompt("auditor")

    triage = state.get("triage_output", {})

    context: dict[str, Any] = {
        "parsed_charges": charges,
        "icd_codes": icd_codes,
        "pricing_results": pricing,
        "billing_rules": billing_rules,
        "rule_summary": rule_summary,
    }
    if triage.get("red_flags"):
        context["triage_red_flags"] = triage["red_flags"]
    if triage.get("analysis_plan"):
        context["triage_analysis_plan"] = triage["analysis_plan"]

    user_message = (
        "Analyze this medical bill for billing errors. "
        "Think through each check carefully using the reasoning process described.\n\n"
        f"DATA:\n{json.dumps(context, indent=2, default=str)}"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    print(f"[Auditor] context size: {len(json.dumps(context))} chars, "
          f"rules loaded: {sum(len(v) for v in billing_rules.values() if isinstance(v, list))}")

    try:
        rate_limit_wait()
        response = llm.invoke(messages)
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
    except Exception as exc:
        print(f"[Auditor] LLM error: {type(exc).__name__}: {exc}")
        return {
            "errors_found": [],
            "error_count": 0,
            "current_agent": "auditor",
            "messages": [],
        }

    print(f"[Auditor] LLM response: {len(raw_text)} chars")

    parsed = extract_json(raw_text)
    if not isinstance(parsed, dict):
        print(f"[Auditor] extract_json returned {type(parsed).__name__}, not dict")
        print(f"[Auditor] raw_text first 500: {raw_text[:500]}")
        parsed = {}

    errors = parsed.get("errors", [])
    print(f"[Auditor] parsed {len(errors)} errors from response")

    cleaned_errors: list[dict[str, Any]] = []
    for err in errors:
        if not isinstance(err, dict):
            continue
        cleaned_errors.append({
            "type": err.get("type", "UNKNOWN"),
            "severity": err.get("severity", "MEDIUM"),
            "description": err.get("description", ""),
            "cpt_codes": err.get("cpt_codes", []),
            "evidence": err.get("evidence", ""),
            "rule_source": err.get("rule_source", ""),
            "potential_savings_low": _safe_float(err.get("potential_savings_low")),
            "potential_savings_high": _safe_float(err.get("potential_savings_high")),
            "confidence": err.get("confidence", "MEDIUM"),
        })

    return {
        "errors_found": cleaned_errors,
        "error_count": len(cleaned_errors),
        "current_agent": "auditor",
        "messages": [response],
    }


def _build_rule_summary(rules: dict[str, Any]) -> str:
    """
    Build a human-readable summary of the billing rules fetched from Supabase.
    This helps the LLM understand what data it has without parsing raw JSON.
    """
    if "_error" in rules:
        return f"WARNING: {rules['_error']} — Auditor will use built-in knowledge only."

    parts: list[str] = []

    dup = rules.get("duplicate", [])
    if dup:
        parts.append(f"DUPLICATE RULES ({len(dup)} loaded): Flag same CPT billed on same date without modifier justification.")

    upcoding = rules.get("upcoding", [])
    if upcoding:
        diag_codes = []
        for r in upcoding:
            tc = r.get("trigger_codes") or {}
            diag_codes.extend(tc.get("diagnosis_codes", []))
        parts.append(
            f"UPCODING RULES ({len(upcoding)} loaded): "
            f"E/M level vs diagnosis complexity checks for ICD-10 codes: {', '.join(diag_codes)}."
        )

    unbundling = rules.get("unbundling", [])
    if unbundling:
        pairs = []
        for r in unbundling:
            tc = r.get("trigger_codes") or {}
            codes = tc.get("cpt_codes", [])
            if len(codes) == 2:
                pairs.append(f"{codes[0]}+{codes[1]}")
        parts.append(
            f"NCCI PTP UNBUNDLING RULES ({len(unbundling)} loaded from real CMS NCCI quarterly data): "
            f"Code pairs that cannot be billed together: {', '.join(pairs[:20])}."
        )

    mue = rules.get("mue", [])
    if mue:
        limits = []
        for r in mue:
            cond = r.get("condition") or {}
            code = cond.get("code", "?")
            max_u = cond.get("max_units", "?")
            limits.append(f"{code}≤{max_u}")
        parts.append(
            f"MUE LIMITS ({len(mue)} loaded from real CMS NCCI quarterly data): "
            f"Max units per date of service: {', '.join(limits[:20])}."
        )

    overcharge = rules.get("overcharge", [])
    if overcharge:
        parts.append(
            f"OVERCHARGE THRESHOLDS ({len(overcharge)} loaded): "
            f"Compare billed amounts against Medicare PFS rates from CMS RVU26B data."
        )

    if not parts:
        return "No billing rules were found for the CPT codes in this bill."

    return "\n".join(parts)


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
