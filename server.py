"""
BillShield — FastAPI Backend

Serves the agent pipeline over HTTP with SSE streaming for real-time
progress updates. Designed to be consumed by the Next.js frontend.

Endpoints:
    POST /analyze/stream      — Run full pipeline, stream SSE events
    POST /dispute/generate    — Trigger dispute letter generation
    GET  /dispute/status/{id} — Poll dispute letter status
    GET  /dispute/download/{id} — Download generated dispute letter
"""

from __future__ import annotations

import asyncio
import io
import json
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from agents.state import BillShieldState
from agents.triage import run_triage
from agents.parser import run_parser
from agents.pricing import run_pricing
from agents.auditor import run_auditor
from agents.researcher import run_researcher
from agents.factchecker import run_factchecker
from agents.writer import run_writer
from tools import db

# ──────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────

app = FastAPI(title="BillShield API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for dispute letter generation status.
# In production this would be backed by a database or task queue.
_dispute_jobs: dict[str, dict[str, Any]] = {}

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _new_state(bill_text: str, session_id: str) -> BillShieldState:
    return {
        "bill_text": bill_text,
        "session_id": session_id,
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


def _safe_persist(session_id: str, updates: dict[str, Any]) -> None:
    try:
        db.update_analysis(session_id, updates)
    except Exception:
        pass


def _extract_text_from_upload(file: UploadFile, content_bytes: bytes) -> str:
    """Extract bill text from uploaded file bytes with PDF-aware parsing."""
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()

    is_pdf = content_type == "application/pdf" or filename.endswith(".pdf")
    is_text = (
        content_type.startswith("text/")
        or filename.endswith(".txt")
        or filename.endswith(".csv")
        or filename.endswith(".md")
    )

    if is_pdf:
        try:
            from pypdf import PdfReader  # type: ignore[reportMissingImports]

            reader = PdfReader(io.BytesIO(content_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages).strip()
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail="PDF parser missing on backend. Install 'pypdf'.",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not extract text from PDF: {exc}",
            ) from exc

    if is_text:
        return content_bytes.decode("utf-8", errors="replace").strip()

    if content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Image OCR is not enabled yet. Please upload a text-based PDF or paste bill text.",
        )

    return content_bytes.decode("utf-8", errors="replace").strip()


def _map_pricing_for_frontend(pricing_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map internal pricing result dicts to the shape the frontend expects."""
    out = []
    for r in pricing_results:
        billed = float(r.get("billed", 0) or 0)
        medicare = float(r.get("medicare_rate", 0) or 0)
        diff = float(r.get("overcharge_amount", billed - medicare) or 0)
        pct = float(r.get("overcharge_pct", 0) or 0)
        out.append({
            "cpt_code": r.get("cpt_code", ""),
            "description": r.get("description", ""),
            "billed_amount": billed,
            "medicare_rate": medicare,
            "fair_estimate": medicare,
            "difference": diff,
            "difference_percent": pct,
        })
    return out


def _map_charges_for_frontend(parsed_charges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map internal parsed charges to the shape the frontend expects."""
    out = []
    for c in parsed_charges:
        out.append({
            "cpt_code": c.get("cpt_code", ""),
            "description": c.get("description", ""),
            "quantity": int(c.get("quantity", 1) or 1),
            "billed_amount": float(c.get("charge", 0) or 0),
        })
    return out


def _map_findings_for_frontend(errors_found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map internal audit findings to the shape the frontend expects."""
    out = []
    for e in errors_found:
        low = float(e.get("potential_savings_low", 0) or 0)
        high = float(e.get("potential_savings_high", 0) or 0)
        out.append({
            "type": str(e.get("type", "other")).lower(),
            "severity": str(e.get("severity", "medium")).lower(),
            "description": e.get("description", ""),
            "cpt_codes": e.get("cpt_codes", []) or [],
            "potential_savings": high if high > 0 else low,
            "evidence": e.get("evidence", ""),
        })
    return out


# ──────────────────────────────────────────────────────────────
# POST /analyze/stream
# ──────────────────────────────────────────────────────────────

PIPELINE_STEPS: list[tuple[str, Any]] = [
    ("triage", run_triage),
    ("parser", run_parser),
    ("pricing", run_pricing),
    ("auditor", run_auditor),
]

DISPUTE_STEPS: list[tuple[str, Any]] = [
    ("researcher", run_researcher),
    ("factchecker", run_factchecker),
    ("writer", run_writer),
]


async def _stream_pipeline(bill_text: str):
    """Generator that runs the agent pipeline and yields SSE events."""

    # Create session
    fallback_id = str(uuid.uuid4())
    try:
        session_id = str(db.create_analysis(bill_text))
    except Exception:
        session_id = fallback_id

    yield _sse({"type": "session_start", "session_id": session_id})

    state = _new_state(bill_text, session_id)
    agents_used: list[str] = []

    # Run core pipeline: triage → parser → pricing → auditor
    for agent_name, agent_fn in PIPELINE_STEPS:
        yield _sse({"type": "agent_start", "agent": agent_name, "timestamp": _ts()})
        try:
            updates = await asyncio.to_thread(agent_fn, state)
            state.update(updates)
            agents_used.append(agent_name)

            # Build agent-specific output for the frontend
            agent_output = _agent_output(agent_name, state)
            yield _sse({
                "type": "agent_complete",
                "agent": agent_name,
                "output": agent_output,
                "timestamp": _ts(),
            })

            _safe_persist(session_id, {
                "status": "processing",
                "parsed_charges": state.get("parsed_charges", []),
                "icd_codes": state.get("icd_codes", []),
                "pricing_analysis": state.get("pricing_results", []),
                "audit_findings": state.get("errors_found", []),
                "total_billed": state.get("total_billed", 0.0),
                "total_fair_rate": state.get("total_fair", 0.0),
                "total_overcharge": state.get("total_overcharge", 0.0),
                "errors_found": state.get("error_count", 0),
            })

        except Exception as exc:
            yield _sse({
                "type": "agent_error",
                "agent": agent_name,
                "error": str(exc),
                "timestamp": _ts(),
            })
            traceback.print_exc()

    # Conditional branch: if errors found, run researcher → factchecker → writer
    # Use error_count from Auditor; fallback to len(errors_found) for robustness
    errors_found = state.get("errors_found", [])
    error_count = int(state.get("error_count", 0) or 0)
    if error_count == 0 and errors_found:
        error_count = len(errors_found)

    if error_count > 0:
        for agent_name, agent_fn in DISPUTE_STEPS:
            yield _sse({"type": "agent_start", "agent": agent_name, "timestamp": _ts()})
            try:
                updates = await asyncio.to_thread(agent_fn, state)
                state.update(updates)
                agents_used.append(agent_name)

                agent_output = _agent_output(agent_name, state)
                yield _sse({
                    "type": "agent_complete",
                    "agent": agent_name,
                    "output": agent_output,
                    "timestamp": _ts(),
                })
            except Exception as exc:
                yield _sse({
                    "type": "agent_error",
                    "agent": agent_name,
                    "error": str(exc),
                    "timestamp": _ts(),
                })
                traceback.print_exc()
    else:
        state["dispute_letter"] = "No billing errors detected. No dispute letter needed."
        for skipped in ("researcher", "factchecker", "writer"):
            yield _sse({
                "type": "agent_skipped",
                "agent": skipped,
                "reason": "No billing errors detected",
                "timestamp": _ts(),
            })

    # Persist final results
    try:
        db.complete_analysis(session_id, {
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
        })
    except Exception:
        pass

    # Final analysis_complete event
    result = {
        "session_id": session_id,
        "status": "complete",
        "total_billed": state.get("total_billed", 0.0),
        "total_fair": state.get("total_fair", 0.0),
        "total_overcharge": state.get("total_overcharge", 0.0),
        "error_count": error_count,
        "parsed_charges": _map_charges_for_frontend(state.get("parsed_charges", [])),
        "pricing_results": _map_pricing_for_frontend(state.get("pricing_results", [])),
        "audit_findings": _map_findings_for_frontend(state.get("errors_found", [])),
        "dispute_letter": state.get("dispute_letter", ""),
        "agents_used": agents_used,
    }

    yield _sse({"type": "analysis_complete", "result": result, "timestamp": _ts()})
    yield "data: [DONE]\n\n"


def _agent_output(agent_name: str, state: BillShieldState) -> dict[str, Any]:
    """Extract the relevant slice of state for a given agent's completion event."""
    if agent_name == "triage":
        return {"analysis_plan": state.get("analysis_plan", "")}
    if agent_name == "parser":
        return {
            "parsed_charges": _map_charges_for_frontend(state.get("parsed_charges", [])),
            "icd_codes": state.get("icd_codes", []),
        }
    if agent_name == "pricing":
        return {
            "pricing_results": _map_pricing_for_frontend(state.get("pricing_results", [])),
            "total_billed": state.get("total_billed", 0.0),
            "total_fair": state.get("total_fair", 0.0),
            "total_overcharge": state.get("total_overcharge", 0.0),
        }
    if agent_name == "auditor":
        return {
            "audit_findings": _map_findings_for_frontend(state.get("errors_found", [])),
            "error_count": state.get("error_count", 0),
        }
    if agent_name == "researcher":
        return {"patient_rights": state.get("patient_rights", [])}
    if agent_name == "factchecker":
        return {"verified_rights": state.get("verified_rights", [])}
    if agent_name == "writer":
        return {"dispute_letter": state.get("dispute_letter", "")}
    return {}


@app.post("/analyze/stream")
async def analyze_stream(
    bill_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """Run the BillShield pipeline and stream SSE events."""
    text = bill_text or ""

    # If a file was uploaded, parse text content appropriately
    if file and not text:
        content_bytes = await file.read()
        text = _extract_text_from_upload(file, content_bytes)

    if not text.strip():
        return PlainTextResponse("bill_text or file is required", status_code=400)

    return StreamingResponse(
        _stream_pipeline(text),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────
# POST /dispute/generate
# ──────────────────────────────────────────────────────────────

@app.post("/dispute/generate")
async def dispute_generate(body: dict[str, Any]):
    """Trigger dispute letter generation for a completed analysis."""
    session_id = body.get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    _dispute_jobs[session_id] = {"status": "pending"}

    # Run in background
    asyncio.create_task(_run_dispute_pipeline(session_id))

    return {"session_id": session_id, "status": "pending"}


async def _run_dispute_pipeline(session_id: str) -> None:
    """Background task: load analysis state from DB and run researcher → factchecker → writer."""
    try:
        _dispute_jobs[session_id] = {"status": "generating"}

        # Load existing analysis from Supabase
        client = db.get_client()
        result = (
            client.table("analysis_results")
            .select("*")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            _dispute_jobs[session_id] = {"status": "error", "error": "Analysis not found"}
            return

        row = result.data[0]

        # Reconstruct state from DB row
        parsed_charges = row.get("parsed_charges") or []
        if isinstance(parsed_charges, str):
            parsed_charges = json.loads(parsed_charges)
        audit_findings = row.get("audit_findings") or []
        if isinstance(audit_findings, str):
            audit_findings = json.loads(audit_findings)
        pricing_analysis = row.get("pricing_analysis") or []
        if isinstance(pricing_analysis, str):
            pricing_analysis = json.loads(pricing_analysis)
        icd_codes = row.get("icd_codes") or []
        if isinstance(icd_codes, str):
            icd_codes = json.loads(icd_codes)

        state = _new_state(row.get("bill_text", ""), session_id)
        state["parsed_charges"] = parsed_charges
        state["errors_found"] = audit_findings
        state["error_count"] = len(audit_findings)
        state["pricing_results"] = pricing_analysis
        state["icd_codes"] = icd_codes
        state["total_billed"] = float(row.get("total_billed", 0) or 0)
        state["total_fair"] = float(row.get("total_fair_rate", 0) or 0)
        state["total_overcharge"] = float(row.get("total_overcharge", 0) or 0)

        # Run the 3 dispute agents
        for agent_fn in (run_researcher, run_factchecker, run_writer):
            updates = await asyncio.to_thread(agent_fn, state)
            state.update(updates)

        letter = state.get("dispute_letter", "")

        # Persist to DB
        _safe_persist(session_id, {
            "dispute_letter": letter,
            "research_findings": state.get("patient_rights", []),
            "verified_rights": state.get("verified_rights", []),
        })

        _dispute_jobs[session_id] = {
            "status": "ready",
            "dispute_letter": letter,
        }

    except Exception as exc:
        traceback.print_exc()
        _dispute_jobs[session_id] = {"status": "error", "error": str(exc)}


# ──────────────────────────────────────────────────────────────
# GET /dispute/status/{session_id}
# ──────────────────────────────────────────────────────────────

@app.get("/dispute/status/{session_id}")
async def dispute_status(session_id: str, request: Request):
    """Poll for dispute letter generation status."""
    job = _dispute_jobs.get(session_id)
    if not job:
        # Check DB for an already-completed letter
        try:
            client = db.get_client()
            result = (
                client.table("analysis_results")
                .select("dispute_letter")
                .eq("session_id", session_id)
                .limit(1)
                .execute()
            )
            if result.data:
                letter = result.data[0].get("dispute_letter", "")
                if letter and letter.strip() and "no dispute letter" not in letter.lower():
                    return {
                        "session_id": session_id,
                        "status": "ready",
                        "download_url": str(request.url_for("dispute_download", session_id=session_id)),
                    }
        except Exception:
            pass
        return {"session_id": session_id, "status": "pending"}

    status = job["status"]
    resp: dict[str, Any] = {"session_id": session_id, "status": status}

    if status == "ready":
        resp["download_url"] = str(request.url_for("dispute_download", session_id=session_id))
    elif status == "error":
        resp["error"] = job.get("error", "Unknown error")

    return resp


# ──────────────────────────────────────────────────────────────
# GET /dispute/download/{session_id}
# ──────────────────────────────────────────────────────────────

@app.get("/dispute/download/{session_id}")
async def dispute_download(session_id: str):
    """Download the generated dispute letter as a text file."""
    letter = ""

    # Check in-memory first
    job = _dispute_jobs.get(session_id)
    if job and job.get("status") == "ready":
        letter = job.get("dispute_letter", "")

    # Fall back to DB
    if not letter:
        try:
            client = db.get_client()
            result = (
                client.table("analysis_results")
                .select("dispute_letter")
                .eq("session_id", session_id)
                .limit(1)
                .execute()
            )
            if result.data:
                letter = result.data[0].get("dispute_letter", "")
        except Exception:
            pass

    if not letter or not letter.strip():
        return PlainTextResponse("Dispute letter not found", status_code=404)

    return PlainTextResponse(
        letter,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="billshield_dispute_letter_{session_id[:8]}.txt"',
        },
    )


# ──────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────

@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "fairmed-api"}
