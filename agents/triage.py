"""
BillShield — Triage (Supervisor) Agent

Model: Nemotron Super 120B (reasoning ON)
Tools: None
Purpose: Read the raw bill, extract metadata, identify red flags,
         and produce an analysis plan for downstream agents.
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


def run_triage(state: BillShieldState) -> dict[str, Any]:
    """Triage node: reads bill text and produces an analysis plan."""
    bill_text = state.get("bill_text", "")
    if not bill_text.strip():
        return {
            "analysis_plan": "No bill text provided.",
            "triage_output": {},
            "current_agent": "triage",
        }

    llm = get_super_llm(max_completion_tokens=2048)
    system_prompt = load_prompt("triage")

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Here is the medical bill to analyze:\n\n{bill_text}"),
    ]

    try:
        rate_limit_wait()
        response = llm.invoke(messages)
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
    except Exception as exc:
        return {
            "analysis_plan": f"Triage failed: {exc}. Downstream agents will process the raw bill.",
            "triage_output": {"error": str(exc)},
            "current_agent": "triage",
        }

    parsed = extract_json(raw_text)
    if not isinstance(parsed, dict):
        parsed = {}

    plan = parsed.get("analysis_plan", raw_text)

    return {
        "analysis_plan": plan if isinstance(plan, str) else json.dumps(plan),
        "triage_output": parsed,
        "current_agent": "triage",
        "messages": [response],
    }
