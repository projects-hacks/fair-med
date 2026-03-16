# Backend API Requirements

The frontend expects the following endpoints from the Python backend.

## Base URL

Set `NEXT_PUBLIC_BACKEND_URL` in frontend `.env` or it defaults to `/api` (proxied via next.config.ts).

---

## 1. Analyze Bill (SSE Stream)

**POST** `/analyze/stream`

Accepts bill text or PDF file, runs the agent pipeline, and streams events via SSE.

### Request

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `bill_text` | string | Either this or file | Raw bill text |
| `file` | File | Either this or text | PDF or image file |

### Response

**Content-Type:** `text/event-stream`

Each event is formatted as:
```
data: {"type": "event_type", ...payload}

```

### Event Types

#### `session_start`
Sent first with the session ID.
```json
{
  "type": "session_start",
  "session_id": "uuid-string"
}
```

#### `agent_start`
Sent when an agent begins processing.
```json
{
  "type": "agent_start",
  "agent": "triage|parser|pricing|auditor|researcher|factchecker|writer",
  "timestamp": "ISO-8601"
}
```

#### `agent_reasoning`
Sent when agent produces reasoning/thinking.
```json
{
  "type": "agent_reasoning",
  "agent": "parser",
  "reasoning": "Extracting CPT codes from the bill text...",
  "timestamp": "ISO-8601"
}
```

#### `agent_tool_call`
Sent when agent calls a tool.
```json
{
  "type": "agent_tool_call",
  "agent": "pricing",
  "tool_call": {
    "name": "lookup_medicare_rate",
    "input": {"cpt_code": "99213"},
    "output": "$125.00",
    "timestamp": "ISO-8601"
  }
}
```

#### `agent_complete`
Sent when agent finishes successfully.
```json
{
  "type": "agent_complete",
  "agent": "parser",
  "output": {
    "parsed_charges": [...],
    "icd_codes": [...]
  },
  "timestamp": "ISO-8601"
}
```

#### `agent_error`
Sent when agent encounters an error.
```json
{
  "type": "agent_error",
  "agent": "researcher",
  "error": "Rate limit exceeded",
  "timestamp": "ISO-8601"
}
```

#### `agent_skipped`
Sent when agent is skipped (e.g., no errors found, so researcher/writer skipped).
```json
{
  "type": "agent_skipped",
  "agent": "researcher",
  "reason": "No billing errors detected",
  "timestamp": "ISO-8601"
}
```

#### `analysis_complete`
Final event with complete results.
```json
{
  "type": "analysis_complete",
  "result": {
    "session_id": "uuid",
    "status": "complete",
    "total_billed": 1500.00,
    "total_fair": 850.00,
    "total_overcharge": 650.00,
    "error_count": 3,
    "parsed_charges": [
      {
        "cpt_code": "99213",
        "description": "Office visit",
        "quantity": 1,
        "billed_amount": 250.00,
        "date_of_service": "2024-01-15"
      }
    ],
    "pricing_results": [
      {
        "cpt_code": "99213",
        "description": "Office visit",
        "billed_amount": 250.00,
        "medicare_rate": 110.00,
        "fair_estimate": 140.00,
        "difference": 110.00,
        "difference_percent": 78.5
      }
    ],
    "audit_findings": [
      {
        "type": "upcoding",
        "severity": "high",
        "description": "99214 billed but documentation supports 99213",
        "cpt_codes": ["99214"],
        "potential_savings": 75.00,
        "evidence": "Documentation shows simple follow-up visit"
      }
    ],
    "agents_used": ["triage", "parser", "pricing", "auditor"]
  }
}
```

---

## 2. Generate Dispute Letter (Async)

**POST** `/dispute/generate`

Triggers dispute letter generation (runs researcher, factchecker, writer agents).

### Request

**Content-Type:** `application/json`

```json
{
  "session_id": "uuid-from-analysis"
}
```

### Response

```json
{
  "session_id": "uuid",
  "status": "pending"
}
```

---

## 3. Dispute Letter Status

**GET** `/dispute/status/{session_id}`

Poll this endpoint to check dispute letter generation status.

### Response

**Pending/Generating:**
```json
{
  "session_id": "uuid",
  "status": "pending|generating"
}
```

**Ready:**
```json
{
  "session_id": "uuid",
  "status": "ready",
  "download_url": "/dispute/download/uuid"
}
```

**Error:**
```json
{
  "session_id": "uuid",
  "status": "error",
  "error": "Failed to verify legal citations"
}
```

---

## 4. Download Dispute Letter

**GET** `/dispute/download/{session_id}`

Returns the generated dispute letter as a downloadable file.

### Response

**Content-Type:** `application/pdf` or `text/plain`
**Content-Disposition:** `attachment; filename="dispute_letter.pdf"`

---

## Agent Names (Enum)

Use these exact names in events:

| Agent | Description |
|-------|-------------|
| `triage` | Initial review, red flag detection |
| `parser` | Extract CPT codes, ICD codes, charges |
| `pricing` | Compare against Medicare rates |
| `auditor` | Detect duplicates, upcoding, unbundling |
| `researcher` | Research patient rights (if errors found) |
| `factchecker` | Verify legal references (if errors found) |
| `writer` | Generate dispute letter (if errors found) |

---

## Example FastAPI Implementation

```python
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Optional
import json
import asyncio

app = FastAPI()

async def event_generator(bill_text: str, file: Optional[UploadFile]):
    session_id = str(uuid.uuid4())
    yield f"data: {json.dumps({'type': 'session_start', 'session_id': session_id})}\n\n"
    
    # Run your LangGraph pipeline here
    # For each agent step, yield events:
    
    yield f"data: {json.dumps({'type': 'agent_start', 'agent': 'triage'})}\n\n"
    
    # ... agent processing ...
    
    yield f"data: {json.dumps({'type': 'agent_reasoning', 'agent': 'triage', 'reasoning': 'Scanning bill for red flags...'})}\n\n"
    
    # ... when complete ...
    
    yield f"data: {json.dumps({'type': 'agent_complete', 'agent': 'triage', 'output': {...}})}\n\n"
    
    # Final result
    yield f"data: {json.dumps({'type': 'analysis_complete', 'result': {...}})}\n\n"

@app.post("/analyze/stream")
async def analyze_stream(
    bill_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    return StreamingResponse(
        event_generator(bill_text, file),
        media_type="text/event-stream"
    )
```

---

## CORS

Enable CORS for frontend origin:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
