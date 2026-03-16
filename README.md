# FairMed

Multi-agent AI system that analyzes medical bills, detects billing errors (duplicates, upcoding, unbundling, overcharges), compares against Medicare fair pricing, and generates a ready-to-send dispute letter.

**NVIDIA Agents for Impact Hackathon | SJSU | March 2026**

## Architecture

7 agents orchestrated by LangGraph:

```
USER → pastes medical bill
       ↓
   [TRIAGE]  → reads bill, identifies red flags, plans strategy
       ↓
   [PARSER]  → extracts CPT codes, ICD-10 diagnoses, charges
       ↓
   [PRICING] → compares each charge against CMS Medicare rates
       ↓
   [AUDITOR] → detects duplicates, upcoding, unbundling, overcharges
       ↓ (errors found?)
   [RESEARCHER] → searches for applicable patient rights & laws
       ↓
   [FACT-CHECKER] → verifies legal references actually apply
       ↓
   [WRITER] → generates dispute letter with evidence
       ↓
   OUTPUT: Report + Dispute Letter
```

## Models

- **NVIDIA Nemotron Super 120B** — reasoning agents (Triage, Auditor, Fact-Checker, Writer)
- **NVIDIA Nemotron Nano 30B** — available for tool-calling tasks

## Data Sources

- **CMS RVU26B April 2026** Medicare Physician Fee Schedule (real rates)
- **CMS NCCI Quarterly PTP Edits** (unbundling rules)
- **CMS NCCI MUE Limits** (max units per service)
- **ICD10API.com** (diagnosis code validation)
- **DuckDuckGo Search** (patient rights research)

## Project Structure

```
fairmed/
├── frontend/              # Next.js 15 app
│   ├── app/              # App router pages
│   ├── components/       # React components
│   └── lib/              # Utilities and types
├── backend/               # FastAPI backend
│   └── main.py           # API endpoints
├── agents/                # Python LangGraph agents
├── tools/                 # Database and API tools
└── prompts/               # Agent system prompts
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, Tailwind CSS |
| Backend | FastAPI (Python) |
| LLM | NVIDIA Nemotron via NIM API |
| Agent Framework | LangGraph (StateGraph) |
| Database | Supabase (PostgreSQL) |
| Deployment | Vercel (Services API) |

## Deploy on Vercel

This project uses Vercel's Services API with two services:
- `frontend/` - Next.js app (route prefix: `/`)
- `backend/` - FastAPI (route prefix: `/api`)

Set these environment variables in Vercel:
- `NVIDIA_API_KEYS` - Your NVIDIA NIM API keys
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase anon key
