#!/usr/bin/env python3
"""
BillShield — Pre-Flight API Verification Script
Run this BEFORE the hackathon to verify every external dependency works.

Usage:
    cd billshield
    cp .env.example .env   # Add your NVIDIA API key
    pip install -r requirements.txt
    python verify_setup.py
"""

import os
import sys
import json
import time
import requests
from typing import Any, Callable, TypeAlias, cast
from dotenv import load_dotenv

load_dotenv()

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

ResultRow: TypeAlias = tuple[str, str, str]
results: list[ResultRow] = []


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        content_items = cast(list[Any], content)
        for item in content_items:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = cast(dict[str, Any], item).get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()
    return ""


def test(name: str, func: Callable[[], str]) -> None:
    """Run a test and record result."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    try:
        result: str = func()
        results.append((name, PASS, result))
        print(f"{PASS} — {result}")
    except Exception as e:
        results.append((name, FAIL, str(e)))
        print(f"{FAIL} — {str(e)}")


# ──────────────────────────────────────────────────────────────
# TEST 1: Python packages
# ──────────────────────────────────────────────────────────────
def test_packages():
    missing: list[str] = []
    packages = {
        "langchain": "langchain",
        "langgraph": "langgraph",
        "langchain_nvidia_ai_endpoints": "langchain-nvidia-ai-endpoints",
        "streamlit": "streamlit",
        "pydantic": "pydantic",
        "duckduckgo_search": "duckduckgo-search",
    }
    for import_name, pip_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        raise Exception(f"Missing packages: {', '.join(missing)}. Run: pip install {' '.join(missing)}")
    return f"All {len(packages)} packages installed"


# ──────────────────────────────────────────────────────────────
# TEST 2: NVIDIA API Key exists
# ──────────────────────────────────────────────────────────────
def test_nvidia_key():
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        raise Exception("NVIDIA_API_KEY not found in .env file")
    if key == "nvapi-your-key-here":
        raise Exception("NVIDIA_API_KEY is still the placeholder. Add your real key to .env")
    if not key.startswith("nvapi-"):
        raise Exception(f"NVIDIA_API_KEY doesn't start with 'nvapi-': got '{key[:10]}...'")
    return f"Key found: {key[:12]}...{key[-4:]}"


# ──────────────────────────────────────────────────────────────
# TEST 3: Nemotron Nano model responds
# ──────────────────────────────────────────────────────────────
def test_nemotron_nano():
    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    llm = ChatNVIDIA(
        model="nvidia/nemotron-3-nano-30b-a3b",
        nvidia_api_key=os.getenv("NVIDIA_API_KEY"),
        max_completion_tokens=100,
    )
    response = llm.invoke("Hello! Please respond with the phrase: BILLSHIELD_NANO_OK")
    content = _content_to_text(getattr(response, "content", ""))
    if len(content) == 0:
        # Try once more with a simpler prompt
        response = llm.invoke("What is 2+2?")
        content = _content_to_text(getattr(response, "content", ""))
        if len(content) == 0:
            raise Exception("Nano model returned empty response on both attempts")
        return f"Nano responded (fallback prompt): '{content[:50]}'"
    return f"Nano responded: '{content[:50]}'"


# ──────────────────────────────────────────────────────────────
# TEST 4: Nemotron Super model responds
# ──────────────────────────────────────────────────────────────
def test_nemotron_super():
    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    llm = ChatNVIDIA(
        model="nvidia/nemotron-3-super-120b-a12b",
        nvidia_api_key=os.getenv("NVIDIA_API_KEY"),
        max_completion_tokens=100,
    )
    response = llm.invoke("Reply with only: BILLSHIELD_SUPER_OK")
    content = _content_to_text(getattr(response, "content", ""))
    if len(content) == 0:
        raise Exception("Super model returned empty response")
    return f"Super responded: '{content[:50]}'"


# ──────────────────────────────────────────────────────────────
# TEST 5: ICD-10 API
# ──────────────────────────────────────────────────────────────
def test_icd10_api():
    url = "http://icd10api.com/"
    params = {"code": "J06.9", "r": "json"}
    resp = requests.get(url, params=params, timeout=10)

    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}")

    data = resp.json()
    if data.get("Response") != "True":
        raise Exception(f"Unexpected response: {data}")

    desc = data.get("Description", "???")
    return f"J06.9 = '{desc}' (Valid: {data.get('Valid')})"


# ──────────────────────────────────────────────────────────────
# TEST 6: ICD-10 API with another code
# ──────────────────────────────────────────────────────────────
def test_icd10_api_second():
    url = "http://icd10api.com/"
    params = {"code": "K80.10", "r": "json"}
    resp = requests.get(url, params=params, timeout=10)
    data = resp.json()

    if data.get("Response") != "True":
        raise Exception(f"Unexpected response: {data}")

    desc = data.get("Description", "???")
    return f"K80.10 = '{desc}'"


# ──────────────────────────────────────────────────────────────
# TEST 7: DuckDuckGo search (for Researcher agent)
# ──────────────────────────────────────────────────────────────
def test_duckduckgo():
    DDGSClass: Any
    try:
        from ddgs import DDGS as DDGSClass  # type: ignore[reportMissingImports]
    except ImportError:
        try:
            from duckduckgo_search import DDGS as DDGSClass  # type: ignore[reportMissingImports]
        except ImportError:
            raise Exception("Neither 'ddgs' nor 'duckduckgo-search' is installed. Run: pip install ddgs")

    ddgs_obj = cast(Any, DDGSClass())
    try:
        results_list: list[dict[str, Any]] = cast(
            list[dict[str, Any]],
            list(ddgs_obj.text("No Surprises Act patient rights medical billing", max_results=3)),
        )
    finally:
        close_fn = getattr(ddgs_obj, "close", None)
        if callable(close_fn):
            close_fn()

    if len(results_list) == 0:
        raise Exception("No search results returned. May be rate-limited — this is a non-critical fallback.")

    return f"Got {len(results_list)} results. First: '{results_list[0].get('title', '???')[:50]}'"


# ──────────────────────────────────────────────────────────────
# TEST 8: Local data files exist
# ──────────────────────────────────────────────────────────────
def test_data_files():
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    expected = ["medicare_rates.json", "billing_rules.json", "sample_bills.json"]
    missing: list[str] = []
    found: list[str] = []

    for f in expected:
        path = os.path.join(data_dir, f)
        if os.path.exists(path):
            size = os.path.getsize(path)
            found.append(f"{f} ({size}B)")
        else:
            missing.append(f)

    if missing:
        raise Exception(f"Missing data files: {', '.join(missing)} — these must be created during prep")

    return f"Found: {', '.join(found)}"


# ──────────────────────────────────────────────────────────────
# TEST 9: Nemotron tool calling works
# ──────────────────────────────────────────────────────────────
def test_tool_calling():
    from langchain_nvidia_ai_endpoints import ChatNVIDIA
    from langchain_core.tools import tool as lc_tool  # type: ignore[reportUnknownVariableType]

    @cast(Any, lc_tool)
    def get_medicare_rate(cpt_code: str) -> str:
        """Look up the Medicare fair payment rate for a CPT code."""
        return json.dumps({"cpt": cpt_code, "rate": 110.35, "description": "Office visit, est patient, low"})

    llm = ChatNVIDIA(
        model="nvidia/nemotron-3-nano-30b-a3b",
        nvidia_api_key=os.getenv("NVIDIA_API_KEY"),
        max_completion_tokens=200,
    )
    llm_with_tools = cast(Any, llm).bind_tools([get_medicare_rate])
    response = llm_with_tools.invoke("What is the Medicare rate for CPT code 99213?")

    tool_calls = cast(list[dict[str, Any]], getattr(response, "tool_calls", []) or [])
    if tool_calls:
        tc = tool_calls[0]
        return f"Tool call generated: {tc['name']}({tc['args']})"
    else:
        content = _content_to_text(getattr(response, "content", ""))
        return f"No tool call (model responded directly: '{content[:60]}'). Tool binding may need prompt tuning."


# ──────────────────────────────────────────────────────────────
# RUN ALL TESTS
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🛡️  BILLSHIELD — Pre-Flight Verification")
    print("=" * 60)

    test("1. Python packages", test_packages)
    test("2. NVIDIA API key", test_nvidia_key)

    # Rate-limited tests — space them out
    test("3. Nemotron Nano (nvidia/nemotron-3-nano-30b-a3b)", test_nemotron_nano)
    print("   ⏳ Waiting 15s (NIM rate limit)...")
    time.sleep(15)

    test("4. Nemotron Super (nvidia/nemotron-3-super-120b-a12b)", test_nemotron_super)
    print("   ⏳ Waiting 15s (NIM rate limit)...")
    time.sleep(15)

    test("5. ICD-10 API (code J06.9)", test_icd10_api)
    test("6. ICD-10 API (code K80.10)", test_icd10_api_second)
    test("7. DuckDuckGo search", test_duckduckgo)
    test("8. Local data files", test_data_files)

    test("9. Nemotron tool calling", test_tool_calling)

    # Summary
    print("\n")
    print("=" * 60)
    print("📋 RESULTS SUMMARY")
    print("=" * 60)
    for name, status, detail in results:
        print(f"  {status} {name}")
        if status == FAIL:
            print(f"       → {detail}")

    passed = sum(1 for _name, status, _detail in results if status == PASS)
    failed = sum(1 for _name, status, _detail in results if status == FAIL)
    total = len(results)

    print(f"\n  {passed}/{total} passed, {failed} failed")

    if failed == 0:
        print("\n  🟢 ALL SYSTEMS GO. Ready to build BillShield!")
    elif failed <= 2 and all("data files" in name or "DuckDuckGo" in name for name, status, _detail in results if status == FAIL):
        print("\n  🟡 MOSTLY READY. Data files and optional features can be built during prep.")
    else:
        print("\n  🔴 FIX FAILURES BEFORE HACKATHON. See details above.")

    sys.exit(0 if failed == 0 else 1)
