"""
FairMed — LangGraph Pipeline

Two-phase architecture:

  Phase 1 (analysis_graph — ~210s):
    START → triage → parser → pricing → auditor ─┐
                                                  ├─ (errors?) → researcher → factchecker → END
                                                  └─ (clean)  → END

  Phase 2 (generate_letter — ~77s, on-demand):
    UI shows analysis results immediately.  User clicks
    "Generate Dispute Letter" → triggers Writer agent async.

Each node is a thin wrapper that:
1. Persists progress to Supabase (analysis_results table)
2. Delegates to the agent function
3. Returns partial state updates
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

def _timed(name, fn, state, persist_data):
    t0 = time.time()
    result = fn(state)
    elapsed = time.time() - t0
    print(f"[{name}] done in {elapsed:.1f}s")
    _persist(state, name.lower(), persist_data(result))
    return result


def _triage_node(state: BillShieldState) -> dict[str, Any]:
    return _timed("Triage", run_triage, state, lambda r: {
        "status": "running", "agents_used": ["triage"],
    })


def _parser_node(state: BillShieldState) -> dict[str, Any]:
    return _timed("Parser", run_parser, state, lambda r: {
        "parsed_charges": r.get("parsed_charges", []),
        "icd_codes": r.get("icd_codes", []),
    })


def _pricing_node(state: BillShieldState) -> dict[str, Any]:
    return _timed("Pricing", run_pricing, state, lambda r: {
        "pricing_analysis": r.get("pricing_results", []),
        "total_billed": r.get("total_billed", 0.0),
    })


def _auditor_node(state: BillShieldState) -> dict[str, Any]:
    return _timed("Auditor", run_auditor, state, lambda r: {
        "audit_findings": r.get("errors_found", []),
        "errors_found": r.get("error_count", 0),
    })


def _researcher_node(state: BillShieldState) -> dict[str, Any]:
    return _timed("Researcher", run_researcher, state, lambda r: {
        "research_findings": r.get("patient_rights", []),
    })


def _factchecker_node(state: BillShieldState) -> dict[str, Any]:
    return _timed("FactChecker", run_factchecker, state, lambda r: {
        "verified_rights": r.get("verified_rights", []),
    })


def _writer_node(state: BillShieldState) -> dict[str, Any]:
    return _timed("Writer", run_writer, state, lambda r: {
        "dispute_letter": r.get("dispute_letter", ""),
        "total_overcharge": state.get("total_overcharge", 0.0),
    })


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
    """Construct the FairMed analysis StateGraph (Phase 1 — no Writer)."""
    builder = StateGraph(BillShieldState)

    builder.add_node("triage", _triage_node)
    builder.add_node("parser", _parser_node)
    builder.add_node("pricing", _pricing_node)
    builder.add_node("auditor", _auditor_node)
    builder.add_node("researcher", _researcher_node)
    builder.add_node("factchecker", _factchecker_node)
    builder.add_node("end_no_errors", _end_no_errors_node)

    builder.add_edge(START, "triage")
    builder.add_edge("triage", "parser")
    builder.add_edge("parser", "pricing")
    builder.add_edge("pricing", "auditor")

    builder.add_conditional_edges(
        "auditor",
        _route_after_auditor,
        {
            "researcher": "researcher",
            "end_no_errors": "end_no_errors",
        },
    )

    builder.add_edge("researcher", "factchecker")
    builder.add_edge("factchecker", END)
    builder.add_edge("end_no_errors", END)

    return builder


def compile_graph():
    """Build and compile the analysis graph."""
    return build_graph().compile()


analysis_graph = compile_graph()

# Backward-compat alias
graph = analysis_graph


# ──────────────────────────────────────────────────────────────
# Phase 1 — analyze_bill (returns results without letter)
# ──────────────────────────────────────────────────────────────

def analyze_bill(bill_text: str, session_id: str | None = None) -> dict[str, Any]:
    """
    Run the analysis pipeline on a medical bill (Phase 1).

    Returns the final state with all findings (charges, pricing,
    errors, rights) but NO dispute letter.  Call generate_letter()
    separately when the user requests one.
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
    final_state = analysis_graph.invoke(initial_state)
    elapsed_ms = int((time.time() - start_time) * 1000)

    final_state["processing_time_ms"] = elapsed_ms

    if session_id:
        try:
            db.complete_analysis(session_id, {
                "total_billed": final_state.get("total_billed", 0.0),
                "total_overcharge": final_state.get("total_overcharge", 0.0),
                "errors_found": final_state.get("error_count", 0),
                "processing_time_ms": elapsed_ms,
            })
        except Exception:
            pass

    return final_state


# ──────────────────────────────────────────────────────────────
# Phase 2 — generate_letter (on-demand, async-friendly)
# ──────────────────────────────────────────────────────────────

def generate_letter(analysis_state: dict[str, Any]) -> str:
    """
    Generate a dispute letter from a completed analysis state (Phase 2).

    Call this AFTER analyze_bill() returns and the user clicks
    "Generate Dispute Letter".  It runs the Writer agent once and
    returns the letter text.

    Args:
        analysis_state: The dict returned by analyze_bill().

    Returns:
        The dispute letter as a string.
    """
    t0 = time.time()
    result = run_writer(analysis_state)
    letter = result.get("dispute_letter", "")
    elapsed = time.time() - t0
    print(f"[Writer] done in {elapsed:.1f}s")

    session_id = analysis_state.get("session_id")
    if session_id:
        try:
            db.update_analysis(session_id, {"dispute_letter": letter})
        except Exception:
            pass

    return letter
