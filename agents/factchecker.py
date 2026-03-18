"""
BillShield — Fact-Checker Agent

Model: Nemotron Super 120B (reasoning ON)
Tools: None (uses reasoning to verify)
Purpose: Verify that cited laws and patient rights actually apply to this case.
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


async def run_factchecker(state: BillShieldState) -> dict[str, Any]:
    """Fact-checker node: verifies applicability of cited rights."""
    rights = state.get("patient_rights", [])
    errors = state.get("errors_found", [])

    if not rights:
        return {
            "verified_rights": [],
            "current_agent": "factchecker",
        }

    bill_text = state.get("bill_text", "")

    llm = get_super_llm(max_completion_tokens=3072)
    system_prompt = load_prompt("factchecker")

    context = {
        "patient_rights": rights,
        "audit_findings": errors,
        "bill_text_snippet": bill_text[:500] if bill_text else "",
    }

    user_message = (
        "Verify whether each of the following cited patient rights and laws "
        "actually applies to this specific billing case. "
        "Think through each one carefully.\n\n"
        f"DATA:\n{json.dumps(context, indent=2, default=str)}"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    try:
        await rate_limit_wait()
        response = await llm.ainvoke(messages)
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
    except Exception as exc:
        return {
            "verified_rights": [{
                **r,
                "status": "PARTIALLY_VERIFIED",
                "verification_notes": f"Verification skipped due to API error: {exc}",
            } for r in rights],
            "current_agent": "factchecker",
        }

    parsed = extract_json(raw_text)
    if not isinstance(parsed, dict):
        parsed = {}

    verified = parsed.get("verified_rights", [])

    kept: list[dict[str, Any]] = []
    for right in verified:
        if not isinstance(right, dict):
            continue
        status = right.get("status", "")
        if status in ("VERIFIED", "PARTIALLY_VERIFIED"):
            kept.append({
                "title": right.get("title", ""),
                "description": right.get("description", ""),
                "source_url": right.get("source_url", ""),
                "applies_to": right.get("applies_to", []),
                "status": status,
                "verification_notes": right.get("verification_notes", ""),
            })

    return {
        "verified_rights": kept,
        "current_agent": "factchecker",
        "messages": [response],
    }
