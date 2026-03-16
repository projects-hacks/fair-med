"""
FastAPI server for BillShield - exposes the LangGraph pipeline as a REST API
Run with: uvicorn server:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

from agents.graph import analyze_bill

app = FastAPI(
    title="BillShield API",
    description="Medical Bill Analysis API powered by LangGraph",
    version="1.0.0"
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    bill_text: str
    session_id: Optional[str] = None


class AnalyzeResponse(BaseModel):
    session_id: str
    bill_text: str
    parsed_charges: list
    icd_codes: list
    pricing_results: list
    errors_found: list
    error_count: int
    total_billed: float
    total_fair: float
    total_overcharge: float
    dispute_letter: str
    patient_rights: list
    verified_rights: list
    agents_used: list


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """Run the full BillShield analysis pipeline on a medical bill."""
    try:
        result = analyze_bill(
            bill_text=request.bill_text,
            session_id=request.session_id
        )
        
        return AnalyzeResponse(
            session_id=result.get("session_id", ""),
            bill_text=request.bill_text,
            parsed_charges=result.get("parsed_charges", []),
            icd_codes=result.get("icd_codes", []),
            pricing_results=result.get("pricing_results", []),
            errors_found=result.get("errors_found", []),
            error_count=result.get("error_count", 0),
            total_billed=result.get("total_billed", 0.0),
            total_fair=result.get("total_fair", 0.0),
            total_overcharge=result.get("total_overcharge", 0.0),
            dispute_letter=result.get("dispute_letter", ""),
            patient_rights=result.get("patient_rights", []),
            verified_rights=result.get("verified_rights", []),
            agents_used=result.get("_agents_used", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
