"""
FastAPI backend for BillShield
Routes requests to the LangGraph agents pipeline
"""
import os
import sys
from typing import Any

# Add parent directory to path so we can import agents
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from root .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import fastapi
import fastapi.middleware.cors
from pydantic import BaseModel

from agents.graph import analyze_bill
from tools import db

app = fastapi.FastAPI()

app.add_middleware(
    fastapi.middleware.cors.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    bill_text: str


class AnalyzeResponse(BaseModel):
    session_id: str
    status: str
    total_billed: float
    total_overcharge: float
    errors_found: int
    parsed_charges: list[dict[str, Any]]
    pricing_results: list[dict[str, Any]]
    audit_findings: list[dict[str, Any]]
    dispute_letter: str
    agents_used: list[str]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Run the full BillShield analysis pipeline on a medical bill.
    Returns comprehensive results including parsed charges, pricing comparison,
    audit findings, and generated dispute letter.
    """
    result = analyze_bill(request.bill_text)
    
    return AnalyzeResponse(
        session_id=result.get("session_id", ""),
        status="complete",
        total_billed=result.get("total_billed", 0.0),
        total_overcharge=result.get("total_overcharge", 0.0),
        errors_found=result.get("error_count", 0),
        parsed_charges=result.get("parsed_charges", []),
        pricing_results=result.get("pricing_results", []),
        audit_findings=result.get("errors_found", []),
        dispute_letter=result.get("dispute_letter", ""),
        agents_used=result.get("_agents_used", []),
    )


@app.get("/history")
async def get_history() -> list[dict[str, Any]]:
    """Get recent analysis history from the database."""
    try:
        return db.get_recent_analyses(limit=20)
    except Exception:
        return []


@app.get("/analysis/{session_id}")
async def get_analysis(session_id: str) -> dict[str, Any]:
    """Get a specific analysis by session ID."""
    try:
        return db.get_analysis(session_id)
    except Exception as e:
        raise fastapi.HTTPException(status_code=404, detail=str(e))
