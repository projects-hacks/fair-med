# Backend API - LIVE

The backend is live at **http://23.239.6.35**

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/analyze` | POST | Start analysis, returns `job_id` |
| `/api/analyze/{job_id}` | GET | Poll for results |
| `/api/letter/{job_id}` | POST | Trigger letter generation |
| `/api/letter/{job_id}` | GET | Poll/get the letter |

---

## 1. Start Analysis

**POST** `http://23.239.6.35/api/analyze`

```json
{
  "bill_text": "Your medical bill text here..."
}
```

**Response:**
```json
{
  "job_id": "uuid-string"
}
```

---

## 2. Poll Analysis Results

**GET** `http://23.239.6.35/api/analyze/{job_id}`

**Response (pending/running):**
```json
{
  "status": "pending" | "running"
}
```

**Response (completed):**
```json
{
  "status": "completed",
  "total_billed": 1500.00,
  "total_fair": 850.00,
  "total_overcharge": 650.00,
  "error_count": 3,
  "parsed_charges": [...],
  "pricing_results": [...],
  "audit_findings": [...],
  "agents_used": ["triage", "parser", "pricing", "auditor"]
}
```

---

## 3. Generate Dispute Letter

**POST** `http://23.239.6.35/api/letter/{job_id}`

Triggers async letter generation.

---

## 4. Get Dispute Letter

**GET** `http://23.239.6.35/api/letter/{job_id}`

Returns letter status or content when ready.

---

## Infrastructure

- 2 pods running on 2 nodes (Linode 4GB each)
- External IP: 23.239.6.35 (Linode NodeBalancer)
- CORS enabled - any frontend can call it directly
