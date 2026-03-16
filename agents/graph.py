"""
BillShield — LangGraph Pipeline

Wires all 7 agents into a StateGraph with conditional routing:

    START → triage → parser → pricing → auditor ─┐
                                                  ├─ (errors found?) ──→ researcher → factchecker → writer → END
                                                  └─ (no errors)     ──→ END

Each node is a thin wrapper that:
1. Persists progress to Supabase (analysis_results table)
2. Delegates to the agent function
3. Returns partial state updates

The compiled graph is exposed as `graph` for use by app.py.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from langgraph.graph import StateGraph, START, END

from .state import BillShieldState
from .triage import run_triage
from .parser import run_parser
from .pricing import run_pricing
from .auditor import run_auditor
from .researcher import run_researcher
from .factchecker import run_factchecker
from .writer import run_writer
from tools import db


# ──────────────────────────────────────────────────────────────
# Node wrappers — persist agent output to Supabase after each step
# ──────────────────────────────────────────────────────────────

def _triage_node(state: BillShieldState) -> dict[str, Any]:
    result = run_triage(state)
    _persist(state, "triage", {
        "status": "running",
        "agents_used": ["triage"],
    })
    return result


def _parser_node(state: BillShieldState) -> dict[str, Any]:
    result = run_parser(state)
    _persist(state, "parser", {
        "parsed_charges": result.get("parsed_charges", []),
        "icd_codes": result.get("icd_codes", []),
    })
    return result


def _pricing_node(state: BillShieldState) -> dict[str, Any]:
    result = run_pricing(state)
    _persist(state, "pricing", {
        "pricing_analysis": result.get("pricing_results", []),
        "total_billed": result.get("total_billed", 0.0),
    })
    return result


def _auditor_node(state: BillShieldState) -> dict[str, Any]:
    result = run_auditor(state)
    _persist(state, "auditor", {
        "audit_findings": result.get("errors_found", []),
        "errors_found": result.get("error_count", 0),
    })
    return result


def _researcher_node(state: BillShieldState) -> dict[str, Any]:
    result = run_researcher(state)
    _persist(state, "researcher", {
        "research_findings": result.get("patient_rights", []),
    })
    return result


def _factchecker_node(state: BillShieldState) -> dict[str, Any]:
    result = run_factchecker(state)
    _persist(state, "factchecker", {
        "verified_rights": result.get("verified_rights", []),
    })
    return result


def _writer_node(state: BillShieldState) -> dict[str, Any]:
    result = run_writer(state)
    _persist(state, "writer", {
        "dispute_letter": result.get("dispute_letter", ""),
        "total_overcharge": state.get("total_overcharge", 0.0),
    })
    return result


# ──────────────────────────────────────────────────────────────
# Conditional routing — skip research/legal phase if no errors found
# ──────────────────────────────────────────────────────────────

def _route_after_auditor(state: BillShieldState) -> Literal["researcher", "end_no_errors"]:
    """If the Auditor found errors, continue to Researcher. Otherwise skip to END."""
    errors = state.get("errors_found", [])
    if errors and len(errors) > 0:
        return "researcher"
    return "end_no_errors"


def _end_no_errors_node(state: BillShieldState) -> dict[str, Any]:
    """Terminal node when no billing errors are found."""
    _persist(state, "complete", {
        "status": "complete",
        "dispute_letter": "No billing errors detected. No dispute letter needed.",
        "total_overcharge": state.get("total_overcharge", 0.0),
        "errors_found": 0,
    })
    return {
        "dispute_letter": "No billing errors detected. No dispute letter needed.",
        "current_agent": "complete",
    }


# ──────────────────────────────────────────────────────────────
# Supabase persistence helper
# ──────────────────────────────────────────────────────────────

def _persist(state: BillShieldState, agent_name: str, updates: dict[str, Any]) -> None:
    """Best-effort persist to Supabase. Failures are silently ignored
    so a DB issue never blocks the pipeline."""
    session_id = state.get("session_id")
    if not session_id:
        return
    try:
        existing_agents = state.get("_agents_used", [])
        if agent_name not in existing_agents:
            existing_agents = existing_agents + [agent_name]
        updates["agents_used"] = existing_agents
        db.update_analysis(session_id, updates)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# Build and compile the graph
# ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct the BillShield StateGraph (uncompiled)."""
    builder = StateGraph(BillShieldState)

    # Add all nodes
    builder.add_node("triage", _triage_node)
    builder.add_node("parser", _parser_node)
    builder.add_node("pricing", _pricing_node)
    builder.add_node("auditor", _auditor_node)
    builder.add_node("researcher", _researcher_node)
    builder.add_node("factchecker", _factchecker_node)
    builder.add_node("writer", _writer_node)
    builder.add_node("end_no_errors", _end_no_errors_node)

    # Sequential pipeline: START → triage → parser → pricing → auditor
    builder.add_edge(START, "triage")
    builder.add_edge("triage", "parser")
    builder.add_edge("parser", "pricing")
    builder.add_edge("pricing", "auditor")

    # Conditional branch after auditor
    builder.add_conditional_edges(
        "auditor",
        _route_after_auditor,
        {
            "researcher": "researcher",
            "end_no_errors": "end_no_errors",
        },
    )

    # Research → fact-check → write → END
    builder.add_edge("researcher", "factchecker")
    builder.add_edge("factchecker", "writer")
    builder.add_edge("writer", END)
    builder.add_edge("end_no_errors", END)

    return builder


def compile_graph():
    """Build and compile the graph, ready to invoke."""
    return build_graph().compile()


# Pre-compiled graph instance for import by app.py
graph = compile_graph()


# ──────────────────────────────────────────────────────────────
# Convenience runner
# ──────────────────────────────────────────────────────────────

def analyze_bill(bill_text: str, session_id: str | None = None) -> dict[str, Any]:
    """
    Run the full BillShield pipeline on a medical bill.

    Args:
        bill_text: Raw text of the itemized medical bill.
        session_id: Optional Supabase session ID for persistence.
                    If None, a new session is created automatically.

    Returns:
        The final state dict containing all analysis results.
    """
    if session_id is None:
        try:
            session_id = db.create_analysis(bill_text)
        except Exception:
            session_id = ""

    initial_state: dict[str, Any] = {
        "bill_text": bill_text,
        "session_id": session_id or "",
    }

    start_time = time.time()
    final_state = graph.invoke(initial_state)
    elapsed_ms = int((time.time() - start_time) * 1000)

    if session_id:
        try:
            db.complete_analysis(session_id, {
                "total_billed": final_state.get("total_billed", 0.0),
                "total_overcharge": final_state.get("total_overcharge", 0.0),
                "errors_found": final_state.get("error_count", 0),
                "processing_time_ms": elapsed_ms,
                "dispute_letter": final_state.get("dispute_letter", ""),
            })
        except Exception:
            pass

    return final_state
