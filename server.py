"""
FairMed — FastAPI Backend Server

Two-phase API:
  POST /api/analyze        → starts analysis, returns job_id
  GET  /api/analyze/{id}   → poll for results
  POST /api/letter/{id}    → trigger letter generation
  GET  /api/letter/{id}    → poll/get the letter
  GET  /api/health         → K8s liveness probe
"""

from __future__ import annotations

import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.graph import analyze_bill, generate_letter

app = FastAPI(title="FairMed API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=4)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalyzeRequest(BaseModel):
    bill_text: str


class AnalyzeResponse(BaseModel):
    job_id: str
    status: JobStatus


class LetterResponse(BaseModel):
    job_id: str
    status: JobStatus
    letter: str | None = None


_jobs: dict[str, dict[str, Any]] = {}


def _run_analysis(job_id: str, bill_text: str) -> None:
    """Runs in a thread — executes the LangGraph analysis pipeline."""
    _jobs[job_id]["status"] = JobStatus.RUNNING
    _jobs[job_id]["started_at"] = time.time()
    try:
        result = analyze_bill(bill_text, session_id=job_id)
        _jobs[job_id]["status"] = JobStatus.COMPLETED
        _jobs[job_id]["result"] = result
        _jobs[job_id]["elapsed_ms"] = int((time.time() - _jobs[job_id]["started_at"]) * 1000)
    except Exception as exc:
        _jobs[job_id]["status"] = JobStatus.FAILED
        _jobs[job_id]["error"] = str(exc)


def _run_letter(job_id: str) -> None:
    """Runs in a thread — generates the dispute letter."""
    analysis = _jobs[job_id]
    analysis["letter_status"] = JobStatus.RUNNING
    try:
        letter = generate_letter(analysis["result"])
        analysis["letter"] = letter
        analysis["letter_status"] = JobStatus.COMPLETED
    except Exception as exc:
        analysis["letter_status"] = JobStatus.FAILED
        analysis["letter_error"] = str(exc)


# ──────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "fairmed-api"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def start_analysis(req: AnalyzeRequest):
    if not req.bill_text.strip():
        raise HTTPException(status_code=400, detail="bill_text is required")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": JobStatus.PENDING,
        "bill_text": req.bill_text,
        "result": None,
        "letter": None,
        "letter_status": None,
    }

    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_analysis, job_id, req.bill_text)

    return AnalyzeResponse(job_id=job_id, status=JobStatus.PENDING)


@app.get("/api/analyze/{job_id}")
async def get_analysis(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    status = job["status"]

    response: dict[str, Any] = {
        "job_id": job_id,
        "status": status,
    }

    if status == JobStatus.COMPLETED:
        result = job["result"]
        response["data"] = {
            "triage": result.get("triage_output", {}),
            "charges": result.get("parsed_charges", []),
            "icd_codes": result.get("icd_codes", []),
            "pricing": result.get("pricing_results", []),
            "total_billed": result.get("total_billed", 0.0),
            "total_fair": result.get("total_fair", 0.0),
            "total_overcharge": result.get("total_overcharge", 0.0),
            "errors": result.get("errors_found", []),
            "error_count": result.get("error_count", 0),
            "patient_rights": result.get("patient_rights", []),
            "verified_rights": result.get("verified_rights", []),
            "processing_time_ms": result.get("processing_time_ms", 0),
        }
        response["has_errors"] = len(result.get("errors_found", [])) > 0
    elif status == JobStatus.FAILED:
        response["error"] = job.get("error", "Unknown error")

    return response


@app.post("/api/letter/{job_id}", response_model=LetterResponse)
async def start_letter(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Analysis not complete yet")

    if not job.get("result", {}).get("errors_found"):
        raise HTTPException(status_code=400, detail="No errors found — letter not needed")

    if job.get("letter_status") == JobStatus.RUNNING:
        return LetterResponse(job_id=job_id, status=JobStatus.RUNNING)

    job["letter_status"] = JobStatus.PENDING
    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _run_letter, job_id)

    return LetterResponse(job_id=job_id, status=JobStatus.PENDING)


@app.get("/api/letter/{job_id}", response_model=LetterResponse)
async def get_letter(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    letter_status = job.get("letter_status")

    if letter_status is None:
        raise HTTPException(status_code=400, detail="Letter generation not started")

    if letter_status == JobStatus.COMPLETED:
        return LetterResponse(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            letter=job.get("letter", ""),
        )

    return LetterResponse(job_id=job_id, status=letter_status)
