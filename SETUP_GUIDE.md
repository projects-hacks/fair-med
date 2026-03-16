# FairMed — Setup Guide

## Step 1: Get Your API Key (only ONE needed!)

### NVIDIA NIM API Key (REQUIRED)

You only need **one API key** for the entire project. Everything else is free with no auth.

```
1. Go to: https://build.nvidia.com
2. Click "Sign In" (top right) → create free NVIDIA developer account
3. After login, go to: https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b
4. Click "Get API Key" button
5. Copy the key (starts with "nvapi-")
6. That's it. This ONE key works for both Nemotron Super and Nano.
```

### Other Services (NO keys needed)

| Service | Auth | Why |
|---------|------|-----|
| **ICD10API** | ❌ No key, no signup | Free public API |
| **DuckDuckGo Search** | ❌ No key, no signup | Uses `duckduckgo-search` Python lib |
| **Medicare Rates** | ❌ No key, no signup | Local JSON file we pre-built |

**Total API keys needed: 1** ✅

---

## Step 2: Set Up the Project

```bash
# Navigate to the project
cd billshield

# Create your .env file from the template
cp .env.example .env

# Open .env and paste your NVIDIA API key
# Replace "nvapi-your-key-here" with your actual key
```

---

## Step 3: Install Dependencies

```bash
# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install all packages
pip install -r requirements.txt
```

If any package fails:
```bash
# Install one at a time to find the issue
pip install langchain
pip install langgraph
pip install langchain-nvidia-ai-endpoints
pip install streamlit
pip install requests pydantic python-dotenv
pip install duckduckgo-search
```

---

## Step 4: Run the Verification Script

```bash
python verify_setup.py
```

This tests ALL 9 dependencies:

```
✅ 1. Python packages        — all 6 packages installed
✅ 2. NVIDIA API key          — key found in .env
✅ 3. Nemotron Nano           — model responds
✅ 4. Nemotron Super          — model responds
✅ 5. ICD-10 API (J06.9)      — returns valid diagnosis
✅ 6. ICD-10 API (K80.10)     — returns valid diagnosis
✅ 7. DuckDuckGo search       — returns search results
❌ 8. Local data files        — EXPECTED FAIL (we haven't built them yet)
✅ 9. Tool calling            — Nemotron generates tool calls

8/9 passed, 1 expected fail
🟡 MOSTLY READY — data files will be created during prep phase.
```

> **⚠️ Test 8 (data files) WILL FAIL right now.** That's expected — we build those files in the next prep phase. Everything else should pass.

> **⚠️ Tests 3-4 take ~30s each** because of NIM rate limits (15s sleep between calls). Total script time: ~2 minutes.

---

## Step 5: Quick Manual Tests (if verify_setup.py has issues)

### Test NVIDIA NIM manually:
```bash
python3 -c "
from langchain_nvidia_ai_endpoints import ChatNVIDIA
import os; from dotenv import load_dotenv; load_dotenv()
llm = ChatNVIDIA(model='nvidia/nemotron-3-nano-30b-a3b')
print(llm.invoke('Say hello').content)
"
```

### Test ICD10API manually:
```bash
curl "http://icd10api.com/?code=J06.9&r=json"
# Should return: {"Name":"J069","Description":"Acute upper respiratory infection..."}
```

### Test DuckDuckGo manually:
```bash
python3 -c "
from duckduckgo_search import DDGS
with DDGS() as d:
    for r in d.text('No Surprises Act medical billing rights', max_results=2):
        print(r['title'])
"
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `NVIDIA_API_KEY not found` | Make sure `.env` exists in `billshield/` dir and has the key |
| `401 Unauthorized` from NIM | Your API key is wrong. Get a new one from build.nvidia.com |
| `429 Rate Limit` from NIM | Free tier = 5 RPM. Wait 15 seconds between calls |
| `pip install fails for langchain-nvidia-ai-endpoints` | Try: `pip install --upgrade pip` first, then retry |
| `ICD10API timeout` | Try a different network. Some campuses block HTTP (not HTTPS) |
| `DuckDuckGo returns 0 results` | Fallback: Researcher agent will use Nemotron's knowledge instead |

---

## What's Next After Setup

Once `verify_setup.py` shows 8/9 or 9/9 passing:

1. **Build data files** (~45 min)
   - `data/medicare_rates.json` — top 200 CPT codes with Medicare rates
   - `data/billing_rules.json` — upcoding/unbundling detection rules
   - `data/sample_bills.json` — 3 demo bills

2. **Build tool wrappers** (~45 min)
   - `tools/icd10_lookup.py`
   - `tools/medicare_pricing.py`
   - `tools/web_search.py`

3. **Write agent prompts + boilerplate** (~60 min)
   - 7 system prompts in `prompts/`
   - State schema, graph skeleton, Streamlit skeleton
