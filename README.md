# FairMed

Multi-agent AI system that analyzes medical bills, detects billing errors (duplicates, upcoding, unbundling, overcharges), compares against Medicare fair pricing, and generates a ready-to-send dispute letter.

**NVIDIA Agents for Impact Hackathon | SJSU | March 2026**

## Architecture

8 agents (7 specialist + 1 supervisor) orchestrated by LangGraph:

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

All Medicare and billing rules data is stored in Supabase, loaded from official CMS releases.

## Quick Start

```bash
cp .env.example .env
# Add your NVIDIA API key and Supabase credentials to .env

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | NVIDIA Nemotron via NIM API |
| Agent Framework | LangGraph (StateGraph) |
| UI | Streamlit |
| Database | Supabase (PostgreSQL) |
| Language | Python 3.11+ |
