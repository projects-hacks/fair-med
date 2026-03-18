"""
BillShield — Parser Agent

Model: Nemotron Super 120B (single reasoning call)
Tools: None (ICD-10 validation done as Python post-step)
Purpose: Extract structured charges and ICD-10 codes from raw bill text.

Architecture: 1 LLM call for extraction + N direct API calls for ICD-10
validation.  No tool-calling loop — deterministic and reliable.
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


def _validate_icd10_codes(codes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate each ICD-10 code via ICD10API in Python (no LLM needed)."""
    import requests

    validated: list[dict[str, Any]] = []
    for entry in codes:
        code = str(entry.get("code", "")).strip()
        if not code:
            continue

        try:
            resp = requests.get(
                "http://icd10api.com/",
                params={"code": code, "r": "json"},
                timeout=5,
            )
            data = resp.json() if resp.ok else {}
        except Exception:
            data = {}

        is_valid = data.get("Response", False) is True
        description = data.get("Description", entry.get("description", "Unknown"))

        validated.append({
            "code": code,
            "description": description,
            "valid": is_valid,
        })
    return validated


async def run_parser(state: BillShieldState) -> dict[str, Any]:
    """Parser node: extracts charges and diagnosis codes from bill text."""
    bill_text = state.get("bill_text", "")
    print(f"[Parser] bill_text length: {len(bill_text)}")
    if not bill_text.strip():
        return {
            "parsed_charges": [],
            "icd_codes": [],
            "bill_metadata": {},
            "current_agent": "parser",
        }

    llm = get_super_llm(max_completion_tokens=4096)
    system_prompt = load_prompt("parser")
    user_message = f"Parse this medical bill and extract all charges and ICD-10 codes:\n\n{bill_text}"

    try:
        await rate_limit_wait()
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ])
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
    except Exception as exc:
        print(f"[Parser] LLM error: {type(exc).__name__}: {exc}")
        return {
            "parsed_charges": [],
            "icd_codes": [],
            "bill_metadata": {"error": str(exc)},
            "current_agent": "parser",
        }

    print(f"[Parser] LLM response: {len(raw_text)} chars")

    parsed = extract_json(raw_text)
    if not isinstance(parsed, dict):
        parsed = {}

    charges = parsed.get("charges", [])
    raw_icd_codes = parsed.get("icd_codes", [])
    metadata = parsed.get("metadata", {})

    for charge in charges:
        if "charge" in charge:
            try:
                charge["charge"] = float(str(charge["charge"]).replace("$", "").replace(",", ""))
            except (ValueError, TypeError):
                charge["charge"] = 0.0
        if "quantity" in charge:
            try:
                charge["quantity"] = int(charge["quantity"])
            except (ValueError, TypeError):
                charge["quantity"] = 1

    icd_codes = _validate_icd10_codes(raw_icd_codes)
    print(f"[Parser] extracted {len(charges)} charges, {len(icd_codes)} ICD codes")

    return {
        "parsed_charges": charges,
        "icd_codes": icd_codes,
        "bill_metadata": metadata if isinstance(metadata, dict) else {},
        "current_agent": "parser",
    }
