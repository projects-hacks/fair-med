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
# 1. Set up environment
cp .env.example .env
# Add your NVIDIA_API_KEYS, SUPABASE_URL, SUPABASE_KEY to .env

# 2. Start Python backend (Terminal 1)
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# 3. Start Next.js frontend (Terminal 2)
npm install
npm run dev
```

Open `http://localhost:3000` - paste a medical bill and click Analyze.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, Tailwind CSS |
| LLM | NVIDIA Nemotron via NIM API |
| Agent Framework | LangGraph (StateGraph) |
| Database | Supabase (PostgreSQL) |
| Language | TypeScript (Frontend), Python 3.11+ (Backend) |

## Project Structure

```
fairmed/
├── app/                    # Next.js app router
│   ├── api/analyze/       # Analysis API endpoint
│   ├── history/           # Analysis history page
│   ├── layout.tsx         # Root layout
│   └── page.tsx           # Main analysis page
├── components/            # React components
│   ├── ui/               # Shadcn UI components
│   ├── bill-input.tsx    # Bill input form
│   ├── pricing-table.tsx # Pricing comparison table
│   └── ...
├── lib/                   # Utilities and types
├── agents/                # Python LangGraph agents
├── tools/                 # Python database and API tools
├── prompts/               # Agent system prompts
└── scripts/               # Database setup scripts
```

## Features

- **Real-time Analysis Pipeline**: Watch each agent process your bill
- **Medicare Fair Rates**: Compare charges against official CMS rates
- **Error Detection**: Identify duplicates, unbundling, upcoding, overcharges
- **Dispute Letter Generation**: AI-generated letters ready to send
- **Secure & Private**: Your data is never stored permanently
