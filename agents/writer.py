"""
BillShield — Appeal Letter Writer Agent

Model: Nemotron Super 120B (long context)
Tools: None
Purpose: Generate a ready-to-send dispute letter with all evidence.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .state import BillShieldState
from ._common import (
    get_super_llm,
    load_prompt,
    rate_limit_wait,
)


async def run_writer(state: BillShieldState) -> dict[str, Any]:
    """Writer node: generates the dispute letter from all findings."""
    errors = state.get("errors_found", [])
    verified_rights = state.get("verified_rights", [])
    charges = state.get("parsed_charges", [])
    pricing = state.get("pricing_results", [])
    icd_codes = state.get("icd_codes", [])
    bill_text = state.get("bill_text", "")

    if not errors:
        return {
            "dispute_letter": "No billing errors were found. No dispute letter is needed.",
            "current_agent": "writer",
        }

    metadata = state.get("bill_metadata") or _extract_bill_metadata(bill_text)

    llm = get_super_llm(max_completion_tokens=8192)
    system_prompt = load_prompt("writer")

    context = {
        "bill_metadata": metadata,
        "parsed_charges": charges,
        "icd_codes": icd_codes,
        "pricing_results": pricing,
        "audit_findings": errors,
        "verified_rights": verified_rights,
        "total_billed": state.get("total_billed", 0.0),
        "total_fair": state.get("total_fair", 0.0),
        "total_overcharge": state.get("total_overcharge", 0.0),
    }

    user_message = (
        "Generate a complete, ready-to-send dispute letter based on the following "
        "billing analysis findings. The letter should be professional, cite specific "
        "charges and dollar amounts, and reference the verified legal protections.\n\n"
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
        print(f"[Writer] LLM error: {exc}")
        return {
            "dispute_letter": _build_fallback_letter(metadata, errors, verified_rights),
            "current_agent": "writer",
        }

    letter = _extract_letter(raw_text)

    return {
        "dispute_letter": letter,
        "current_agent": "writer",
        "messages": [response],
    }


def _extract_letter(raw_text: str) -> str:
    """Extract the dispute letter from LLM response, handling thinking tags."""
    outside_thinking = re.sub(
        r"<thinking>.*?</thinking>", "", raw_text, flags=re.DOTALL
    ).strip()

    if len(outside_thinking) > 100:
        text = outside_thinking
    else:
        match = re.search(r"</thinking>\s*(.*)", raw_text, flags=re.DOTALL)
        if match and len(match.group(1).strip()) > 100:
            text = match.group(1).strip()
        else:
            text = raw_text

    text = re.sub(r"</?thinking>", "", text).strip()

    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    return text


def _extract_bill_metadata(bill_text: str) -> dict[str, Any]:
    """Best-effort extraction of basic metadata from bill text for the letter header."""
    metadata: dict[str, Any] = {
        "patient_name": None,
        "account_number": None,
        "facility": None,
        "date_of_service": None,
    }

    if not bill_text:
        return metadata

    lines = bill_text.split("\n")
    for line in lines:
        upper = line.upper().strip()
        if "PATIENT:" in upper:
            metadata["patient_name"] = line.split(":", 1)[-1].strip()
        elif "ACCOUNT" in upper and ("NO" in upper or "#" in upper or "NUMBER" in upper):
            metadata["account_number"] = line.split(":", 1)[-1].strip()
        elif "DATE OF SERVICE" in upper:
            metadata["date_of_service"] = line.split(":", 1)[-1].strip()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("=") and not stripped.startswith("-"):
            metadata["facility"] = stripped
            break

    return metadata


def _build_fallback_letter(
    metadata: dict[str, Any],
    errors: list[dict[str, Any]],
    rights: list[dict[str, Any]],
) -> str:
    """Generate a basic dispute letter when the LLM API call fails."""
    patient = metadata.get("patient_name") or "[Patient Name]"
    account = metadata.get("account_number") or "[Account Number]"
    facility = metadata.get("facility") or "[Provider Name]"
    dos = metadata.get("date_of_service") or "[Date of Service]"

    lines = [
        f"To: {facility} Billing Department",
        f"From: {patient}",
        f"Re: Formal Dispute — Account {account} — Date of Service {dos}",
        "",
        "Dear Billing Department,",
        "",
        "I am writing to formally dispute the following charges on my medical bill:",
        "",
    ]

    for i, err in enumerate(errors, 1):
        lines.append(
            f"{i}. {err.get('type', 'ERROR')}: {err.get('description', 'Billing error detected')} "
            f"(CPT: {', '.join(err.get('cpt_codes', []))})"
        )

    lines.append("")
    lines.append("I request a written response within 30 days.")
    lines.append("")
    lines.append(f"Sincerely,\n{patient}")

    return "\n".join(lines)
