from __future__ import annotations

import time
import uuid
from typing import Any, cast

import streamlit as st

from agents.auditor import run_auditor
from agents.factchecker import run_factchecker
from agents.parser import run_parser
from agents.pricing import run_pricing
from agents.researcher import run_researcher
from agents.triage import run_triage
from agents.writer import run_writer
from agents.state import BillShieldState
from tools import db

db_api: Any = db
st_api: Any = st


APP_TITLE = "🛡️ BillShield"
APP_TAGLINE = "AI-powered medical bill audit with real CMS pricing + NCCI rules"

DEMO_BILL_TEXT = """Valley Regional Medical Center
Patient: Jane Doe
Account Number: VRMC-2026-0316-1007
Date of Service: 03/10/2026

Charges:
- CPT 99214 Office/Outpatient Visit (Established) x1 .......... $420.00
- CPT 80053 Comprehensive Metabolic Panel x1 ................... $210.00
- CPT 80048 Basic Metabolic Panel x1 ........................... $185.00
- CPT 85025 CBC with Differential x1 ........................... $160.00
- CPT 85027 CBC Automated x1 ................................... $145.00
- CPT 93000 Electrocardiogram x1 ............................... $280.00

Diagnoses:
- J06.9 Acute upper respiratory infection, unspecified
- Z23 Encounter for immunization
"""


def _init_state() -> None:
    if "bill_text" not in st.session_state:
        st.session_state.bill_text = ""
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None


def _new_state(bill_text: str) -> BillShieldState:
    return {
        "bill_text": bill_text,
        "session_id": str(uuid.uuid4()),
        "analysis_plan": "",
        "triage_output": {},
        "parsed_charges": [],
        "icd_codes": [],
        "bill_metadata": {},
        "pricing_results": [],
        "total_billed": 0.0,
        "total_fair": 0.0,
        "total_overcharge": 0.0,
        "errors_found": [],
        "error_count": 0,
        "patient_rights": [],
        "verified_rights": [],
        "dispute_letter": "",
        "current_agent": "idle",
        "messages": [],
    }


def _safe_create_analysis(bill_text: str, fallback_id: str) -> str:
    try:
        return str(db_api.create_analysis(bill_text))
    except Exception:
        return fallback_id


def _safe_update_analysis(session_id: str, updates: dict[str, Any]) -> None:
    try:
        db_api.update_analysis(session_id, updates)
    except Exception:
        pass


def _safe_complete_analysis(session_id: str, updates: dict[str, Any]) -> None:
    try:
        db_api.complete_analysis(session_id, updates)
    except Exception:
        pass


def _run_pipeline(bill_text: str) -> BillShieldState:
    state = _new_state(bill_text)
    state["session_id"] = _safe_create_analysis(bill_text, state["session_id"])

    steps: list[tuple[str, Any, int]] = [
        ("Triage", run_triage, 1),
        ("Parser", run_parser, 2),
        ("Pricing", run_pricing, 3),
        ("Auditor", run_auditor, 4),
    ]

    progress = st.progress(0, text="Initializing analysis...")
    with st.status("Running BillShield agent pipeline...", expanded=True) as status:
        for label, func, idx in steps:
            status.write(f"▶️ {label} agent running...")
            started = time.time()
            updates = func(state)
            state.update(updates)
            elapsed = time.time() - started
            status.write(f"✅ {label} completed in {elapsed:.1f}s")
            progress.progress(int((idx / 7) * 100), text=f"{label} complete")

            _safe_update_analysis(
                state["session_id"],
                {
                    "status": "processing",
                    "parsed_charges": state.get("parsed_charges", []),
                    "icd_codes": state.get("icd_codes", []),
                    "pricing_analysis": state.get("pricing_results", []),
                    "audit_findings": state.get("errors_found", []),
                    "total_billed": state.get("total_billed", 0.0),
                    "total_fair_rate": state.get("total_fair", 0.0),
                    "total_overcharge": state.get("total_overcharge", 0.0),
                    "errors_found": state.get("error_count", 0),
                },
            )

        if int(state.get("error_count", 0)) > 0:
            branch_steps: list[tuple[str, Any, int]] = [
                ("Researcher", run_researcher, 5),
                ("Fact-Checker", run_factchecker, 6),
                ("Writer", run_writer, 7),
            ]
            for label, func, idx in branch_steps:
                status.write(f"▶️ {label} agent running...")
                started = time.time()
                updates = func(state)
                state.update(updates)
                elapsed = time.time() - started
                status.write(f"✅ {label} completed in {elapsed:.1f}s")
                progress.progress(int((idx / 7) * 100), text=f"{label} complete")
        else:
            state["dispute_letter"] = "No billing errors were detected, so a dispute letter is not required."
            status.write("ℹ️ No major billing errors found. Research, fact-check, and letter steps skipped.")
            progress.progress(100, text="Analysis complete")

        status.update(label="✅ Analysis complete", state="complete", expanded=False)

    _safe_complete_analysis(
        state["session_id"],
        {
            "summary": "BillShield analysis completed",
            "pricing_analysis": state.get("pricing_results", []),
            "audit_findings": state.get("errors_found", []),
            "research_findings": state.get("patient_rights", []),
            "verified_rights": state.get("verified_rights", []),
            "dispute_letter": state.get("dispute_letter", ""),
            "total_billed": state.get("total_billed", 0.0),
            "total_fair_rate": state.get("total_fair", 0.0),
            "total_overcharge": state.get("total_overcharge", 0.0),
            "errors_found": state.get("error_count", 0),
        },
    )

    return state


def _render_error_cards(errors_found: list[dict[str, Any]]) -> None:
    if not errors_found:
        st.success("No high-confidence billing errors were found.")
        return

    st.subheader("Error Findings")
    for item in errors_found:
        severity = str(item.get("severity", "MEDIUM")).upper()
        label = f"{severity} · {item.get('type', 'UNKNOWN')}"
        body = item.get("description", "No description provided.")
        cpts = ", ".join(item.get("cpt_codes", []) or [])
        low = float(item.get("potential_savings_low", 0) or 0)
        high = float(item.get("potential_savings_high", 0) or 0)

        if severity == "HIGH":
            box = st.error
        elif severity == "MEDIUM":
            box = st.warning
        else:
            box = st.info

        with st.container(border=True):
            box(label)
            st.write(body)
            if cpts:
                st.caption(f"CPT/HCPCS: {cpts}")
            if low > 0 or high > 0:
                st.caption(f"Potential savings: ${low:,.2f} – ${high:,.2f}")


def _render_pricing_table(pricing_results: list[dict[str, Any]]) -> None:
    st.subheader("Pricing Comparison")
    if not pricing_results:
        st.info("No pricing results available.")
        return

    rows: list[dict[str, Any]] = []
    for row in pricing_results:
        billed = float(row.get("billed", 0) or 0)
        fair = float(row.get("medicare_rate", 0) or 0)
        diff = float(row.get("difference", billed - fair) or 0)
        pct_over = float(row.get("pct_over", 0) or 0)
        rows.append(
            {
                "CPT": row.get("cpt_code") or row.get("cpt") or "",
                "Description": row.get("description", ""),
                "Qty": row.get("quantity", 1),
                "Billed ($)": round(billed, 2),
                "Medicare Fair ($)": round(fair, 2),
                "Difference ($)": round(diff, 2),
                "% Over": round(pct_over, 1),
            }
        )

    st_api.dataframe(rows, use_container_width=True)


def _load_demo_bill_from_db() -> str:
    try:
        bills = cast(list[dict[str, Any]], db_api.get_sample_bills())
        if bills:
            first = bills[0]
            text = first.get("bill_text")
            if isinstance(text, str) and text.strip():
                return text
    except Exception:
        pass
    return DEMO_BILL_TEXT


def main() -> None:
    st.set_page_config(page_title="BillShield", page_icon="🛡️", layout="wide")
    _init_state()

    st.title(APP_TITLE)
    st.caption(APP_TAGLINE)

    with st.sidebar:
        st.header("About")
        st.write("Built for SJSU hackathon: fast, evidence-backed medical billing audits.")
        st.write("Models: Nemotron Nano + Super")
        st.write("Data: CMS RVU26B + NCCI 2026Q2")

    left, right = st.columns([3, 1])
    with left:
        bill_text_value = cast(str, st.session_state.bill_text or "")
        st.session_state.bill_text = st.text_area(
            "Paste medical bill text",
            value=bill_text_value,
            height=260,
            placeholder="Paste EOB or itemized bill text here...",
        )
    with right:
        if st.button("Try Demo Bill", use_container_width=True):
            st.session_state.bill_text = _load_demo_bill_from_db()
            st.rerun()
        analyze = st.button("Analyze Bill", type="primary", use_container_width=True)

    if analyze:
        bill_text_to_analyze = st.session_state.bill_text or ""
        if not bill_text_to_analyze.strip():
            st.warning("Please enter a bill first.")
        else:
            st.session_state.analysis_result = _run_pipeline(bill_text_to_analyze)

    result = st.session_state.analysis_result
    if not result:
        st.info("Run an analysis to see pricing, errors, and draft dispute letter.")
        return

    st.divider()
    st.subheader("Results")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Billed", f"${float(result.get('total_billed', 0) or 0):,.2f}")
    m2.metric("Medicare Fair", f"${float(result.get('total_fair', 0) or 0):,.2f}")
    m3.metric("Overcharge", f"${float(result.get('total_overcharge', 0) or 0):,.2f}")
    m4.metric("Errors Found", str(int(result.get("error_count", 0) or 0)))

    _render_pricing_table(result.get("pricing_results", []))
    _render_error_cards(result.get("errors_found", []))

    with st.expander("Dispute Letter", expanded=True):
        letter = str(result.get("dispute_letter", "")).strip()
        if not letter:
            st.info("No dispute letter generated.")
        else:
            st.text_area("Draft", value=letter, height=360)
            st.download_button(
                "Download Letter (.txt)",
                data=letter.encode("utf-8"),
                file_name="billshield_dispute_letter.txt",
                mime="text/plain",
            )


if __name__ == "__main__":
    main()
