from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class BillShieldState(TypedDict):
    """Shared state flowing through every node in the BillShield graph."""

    # ── Input ──
    bill_text: str

    # ── Session tracking (Supabase analysis_results) ──
    session_id: str

    # ── Triage ──
    analysis_plan: str
    triage_output: dict[str, Any]

    # ── Parser ──
    parsed_charges: list[dict[str, Any]]
    icd_codes: list[dict[str, Any]]
    bill_metadata: dict[str, Any]

    # ── Pricing ──
    pricing_results: list[dict[str, Any]]
    total_billed: float
    total_fair: float
    total_overcharge: float

    # ── Auditor ──
    errors_found: list[dict[str, Any]]
    error_count: int

    # ── Researcher ──
    patient_rights: list[dict[str, Any]]

    # ── Fact-Checker ──
    verified_rights: list[dict[str, Any]]

    # ── Writer ──
    dispute_letter: str

    # ── Meta / UI progress ──
    current_agent: str
    messages: Annotated[list[AnyMessage], add_messages]
