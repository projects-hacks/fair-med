"""
BillShield — Researcher Agent

Model: Nemotron Super 120B (single reasoning call)
Tools: None (web searches done as Python pre-step)
Purpose: Find applicable patient rights and laws for the dispute.

Architecture: N DuckDuckGo searches in Python, then 1 LLM call to
analyze relevance.  No tool-calling loop.
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
from tools.web_search import _run_ddg_search


_SEARCH_QUERIES_BY_ERROR = {
    "OVERCHARGE": "No Surprises Act protections excessive medical billing charges",
    "UPCODING": "federal False Claims Act upcoding medical billing patient rights",
    "DUPLICATE": "CMS NCCI correct coding initiative duplicate billing rules patient",
    "UNBUNDLING": "NCCI PTP edits unbundling medical billing patient rights",
    "MUE_VIOLATION": "CMS medically unlikely edits MUE patient billing dispute",
}

_FALLBACK_RIGHTS = [
    {
        "title": "No Surprises Act (2022)",
        "url": "https://www.cms.gov/nosurprises",
        "snippet": "Federal law protecting patients from surprise out-of-network bills "
                   "and providing billing dispute resolution processes.",
    },
    {
        "title": "California Fair Billing Act",
        "url": "https://oag.ca.gov/consumers/general/medical-billing",
        "snippet": "State protections limiting what hospitals may bill uninsured and "
                   "underinsured patients, requiring financial assistance policies.",
    },
]


def _run_searches(error_types: list[str], state_hint: str) -> list[dict[str, Any]]:
    """Execute targeted DuckDuckGo searches based on error types found."""
    all_results: list[dict[str, Any]] = []
    queries_used: list[str] = []

    for etype in error_types:
        query = _SEARCH_QUERIES_BY_ERROR.get(etype)
        if query:
            results = _run_ddg_search(query, max_results=3)
            all_results.extend(results)
            queries_used.append(query)

    if state_hint:
        state_query = f"{state_hint} medical billing patient protection laws"
        results = _run_ddg_search(state_query, max_results=3)
        all_results.extend(results)
        queries_used.append(state_query)

    if not all_results:
        all_results = _FALLBACK_RIGHTS
        queries_used.append("(fallback — search returned no results)")

    print(f"[Researcher] {len(queries_used)} searches → {len(all_results)} results")
    return all_results


def run_researcher(state: BillShieldState) -> dict[str, Any]:
    """Researcher node: searches for applicable patient billing rights."""
    errors = state.get("errors_found", [])
    if not errors:
        return {
            "patient_rights": [],
            "current_agent": "researcher",
        }

    bill_text = state.get("bill_text", "")
    error_types = list({e.get("type", "") for e in errors})

    state_hint = ""
    for name in ["California", "CA", "Texas", "TX", "New York", "NY", "Florida", "FL"]:
        if name in bill_text:
            state_hint = name
            break

    search_results = _run_searches(error_types, state_hint)

    llm = get_super_llm(max_completion_tokens=4096)
    system_prompt = load_prompt("researcher")

    context = {
        "billing_errors": [
            {"type": e.get("type"), "severity": e.get("severity"),
             "description": e.get("description"), "cpt_codes": e.get("cpt_codes")}
            for e in errors
        ],
        "search_results": search_results,
        "facility_state": state_hint or "unknown",
    }

    user_message = (
        "Based on the billing errors found and the search results below, "
        "identify which patient rights and laws apply to this case.\n\n"
        f"DATA:\n{json.dumps(context, indent=2, default=str)}"
    )

    try:
        rate_limit_wait()
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ])
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
    except Exception as exc:
        print(f"[Researcher] LLM error: {type(exc).__name__}: {exc}")
        return {
            "patient_rights": [{
                "title": "No Surprises Act (2022)",
                "description": "Federal law protecting patients from surprise medical bills.",
                "source_url": "https://www.cms.gov/nosurprises",
                "applies_to": error_types,
                "relevance": "HIGH",
            }],
            "current_agent": "researcher",
        }

    parsed = extract_json(raw_text)
    if not isinstance(parsed, dict):
        parsed = {}

    rights = parsed.get("rights", [])
    cleaned_rights: list[dict[str, Any]] = []
    for right in rights:
        if not isinstance(right, dict):
            continue
        cleaned_rights.append({
            "title": right.get("title", "Unknown"),
            "description": right.get("description", ""),
            "source_url": right.get("source_url", ""),
            "applies_to": right.get("applies_to", []),
            "relevance": right.get("relevance", "MEDIUM"),
        })

    print(f"[Researcher] {len(cleaned_rights)} applicable rights identified")

    return {
        "patient_rights": cleaned_rights,
        "current_agent": "researcher",
    }
