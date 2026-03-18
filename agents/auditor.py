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
    _extract_content,
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


async def run_auditor(state: BillShieldState) -> dict[str, Any]:
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

    # Use enable_thinking=False so Nemotron returns direct JSON instead of
    # putting output in <thinking> tags (which can result in empty content)
    llm = get_super_llm(max_completion_tokens=8192)
    system_prompt = load_prompt("auditor")
    # Prepend reasoning-off hint for Nemotron Super (reduces empty responses)
    system_prompt = "detailed thinking off\n\n" + system_prompt

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
        await rate_limit_wait()
        response = await llm.ainvoke(messages)
        raw_text = _extract_content(response)
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

    # Fallback: when LLM returns 0 errors but triage flagged issues or pricing shows MAJOR overcharges
    if not errors and (triage.get("red_flags") or _has_major_overcharges(pricing)):
        errors = _infer_errors_from_triage(state, pricing, charges)
        if errors:
            print(f"[Auditor] fallback: inferred {len(errors)} errors from triage + pricing")

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


def _has_major_overcharges(pricing: list) -> bool:
    """True if any charge has MAJOR or EXTREME severity."""
    for p in pricing or []:
        if isinstance(p, dict) and p.get("severity") in ("MAJOR", "EXTREME"):
            return True
    return False


def _infer_errors_from_triage(
    state: BillShieldState,
    pricing: list,
    charges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Infer billing errors from triage red flags and pricing when LLM returns empty.
    Maps red-flag patterns to error types and adds MAJOR overcharges from pricing.
    """
    errors: list[dict[str, Any]] = []
    triage = state.get("triage_output", {})
    red_flags = triage.get("red_flags", [])
    pricing_by_cpt = {str(p.get("cpt_code", "")): p for p in (pricing or []) if isinstance(p, dict) and p.get("cpt_code")}

    # Map red-flag substrings to error type
    flag_to_type = [
        ("duplicate", "DUPLICATE"),
        ("99213 appears twice", "DUPLICATE"),
        ("upcoding", "UPCODING"),
        ("99215", "UPCODING"),
        ("unbundling", "UNBUNDLING"),
        ("BMP", "UNBUNDLING"),
        ("CMP", "UNBUNDLING"),
        ("overlapping lab", "UNBUNDLING"),
    ]

    seen_types: set[str] = set()
    for flag in red_flags:
        flag_lower = (flag or "").lower()
        for pattern, etype in flag_to_type:
            if pattern.lower() in flag_lower and etype not in seen_types:
                seen_types.add(etype)
                # Infer CPT codes from flag text
                cpt_codes: list[str] = []
                if "99213" in flag:
                    cpt_codes = ["99213"]
                elif "99215" in flag:
                    cpt_codes = ["99215"]
                elif "80048" in flag or "80053" in flag or "BMP" in flag or "CMP" in flag:
                    cpt_codes = ["80048", "80053"]
                errors.append({
                    "type": etype,
                    "severity": "HIGH",
                    "description": flag[:200],
                    "cpt_codes": cpt_codes or [],
                    "evidence": f"Triage red flag: {flag[:150]}",
                    "rule_source": "Triage fallback",
                    "potential_savings_low": 0.0,
                    "potential_savings_high": 0.0,
                    "confidence": "MEDIUM",
                })
                break

    # Add MAJOR/EXTREME overcharges from pricing
    for p in pricing or []:
        if not isinstance(p, dict):
            continue
        sev = p.get("severity")
        if sev not in ("MAJOR", "EXTREME"):
            continue
        cpt = str(p.get("cpt_code", ""))
        billed = _safe_float(p.get("billed"))
        medicare = _safe_float(p.get("medicare_rate"))
        savings = billed - medicare if billed and medicare else 0.0
        # Avoid duplicate OVERCHARGE for same CPT
        if any(e.get("type") == "OVERCHARGE" and cpt in e.get("cpt_codes", []) for e in errors):
            continue
        errors.append({
            "type": "OVERCHARGE",
            "severity": "HIGH",
            "description": f"{cpt} billed ${billed:.2f} vs Medicare ${medicare:.2f} ({sev})",
            "cpt_codes": [cpt],
            "evidence": f"Pricing: {sev} overcharge",
            "rule_source": "CMS PFS RVU26B",
            "potential_savings_low": savings,
            "potential_savings_high": savings,
            "confidence": "HIGH",
        })

    return errors


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
