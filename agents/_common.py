"""
Shared utilities for all BillShield agents.

Provides LLM initialization, API key rotation, prompt loading,
JSON extraction, and rate-limit handling.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

warnings.filterwarnings("ignore", message=".*available_models.*type is unknown.*")

from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

sys.stdout.reconfigure(line_buffering=True)

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

NEMOTRON_SUPER = "nvidia/nemotron-3-super-120b-a12b"
NEMOTRON_NANO = "nvidia/nemotron-3-nano-30b-a3b"

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# ──────────────────────────────────────────────────────────────
# API Key Rotation (lazy-loaded so import doesn't crash without .env)
# ──────────────────────────────────────────────────────────────

_api_keys: list[str] | None = None
_key_cycle: itertools.cycle | None = None


def _ensure_api_keys() -> list[str]:
    """Load API keys on first use, not at import time.

    Supports both NVIDIA_API_KEYS and NVIDIA_API_KEY (singular or
    comma-separated).  With N keys we get N × 5 RPM effective throughput.
    """
    global _api_keys, _key_cycle
    if _api_keys is not None:
        return _api_keys

    raw = os.getenv("NVIDIA_API_KEYS", "") or os.getenv("NVIDIA_API_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if keys:
        _api_keys = keys
        _key_cycle = itertools.cycle(_api_keys)
        print(f"[FairMed] Loaded {len(_api_keys)} NVIDIA API key(s) "
              f"→ effective rate ~{len(_api_keys) * _RPM_LIMIT} RPM")
        return _api_keys

    raise ValueError("Set NVIDIA_API_KEY or NVIDIA_API_KEYS in .env")


def get_next_api_key() -> str:
    """Round-robin through available NVIDIA API keys."""
    _ensure_api_keys()
    assert _key_cycle is not None
    return next(_key_cycle)


# ──────────────────────────────────────────────────────────────
# Rate Limiting
# ──────────────────────────────────────────────────────────────

import asyncio

def _ts() -> str:
    # We will reuse this if needed, or just let time.time() be used locally
    pass

_last_call_time: float = 0.0
_RPM_LIMIT = int(os.getenv("NIM_RPM", "40"))


async def rate_limit_wait() -> None:
    """Sleep if needed to stay within NIM rate limits.

    Default 40 RPM (per build.nvidia.com). Override with NIM_RPM env var.
    With N keys, effective RPM = N * NIM_RPM.
    At 40+ RPM, API response time naturally keeps us under the limit.
    """
    global _last_call_time
    keys = _ensure_api_keys()
    effective_rpm = len(keys) * _RPM_LIMIT
    if effective_rpm >= 40:
        _last_call_time = time.time()
        return
    interval = 60.0 / effective_rpm
    elapsed = time.time() - _last_call_time
    if elapsed < interval:
        await asyncio.sleep(interval - elapsed)
    _last_call_time = time.time()


# ──────────────────────────────────────────────────────────────
# LLM Initialization
# ──────────────────────────────────────────────────────────────

def get_super_llm(**kwargs: Any) -> ChatNVIDIA:
    """Get a Nemotron Super 120B instance (reasoning model)."""
    defaults: dict[str, Any] = {
        "model": NEMOTRON_SUPER,
        "nvidia_api_key": get_next_api_key(),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_completion_tokens": 4096,
    }
    defaults.update(kwargs)
    return ChatNVIDIA(**defaults)


def get_nano_llm(**kwargs: Any) -> ChatNVIDIA:
    """Get a Nemotron Nano 30B instance (tool-calling model)."""
    defaults: dict[str, Any] = {
        "model": NEMOTRON_NANO,
        "nvidia_api_key": get_next_api_key(),
        "temperature": 1.0,
        "top_p": 0.95,
        "max_completion_tokens": 4096,
    }
    defaults.update(kwargs)
    return ChatNVIDIA(**defaults)


# ──────────────────────────────────────────────────────────────
# Prompt Loading
# ──────────────────────────────────────────────────────────────

def load_prompt(agent_name: str) -> str:
    """Read a system prompt from prompts/{agent_name}.md."""
    path = PROMPTS_DIR / f"{agent_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────
# JSON Extraction
# ──────────────────────────────────────────────────────────────

def extract_json(text: str) -> dict[str, Any] | list[Any]:
    """
    Extract the first JSON object or array from LLM output.

    Handles markdown fenced code blocks, stray text before/after,
    and content inside <thinking> tags (reasoning models may put JSON there).
    """
    if not text:
        return {}

    # Strip <thinking>...</thinking> tags from reasoning models
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()

    # Also extract content from inside thinking (model may put JSON there)
    thinking_match = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
    inside_thinking = thinking_match.group(1).strip() if thinking_match else ""

    # Try: cleaned (no thinking), full text, then inside thinking
    for candidate in [cleaned, text, inside_thinking]:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass

    # Try to find JSON inside markdown code fences (check both cleaned and inside_thinking)
    for search_text in [cleaned, inside_thinking]:
        if not search_text:
            continue
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", search_text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

    # Try to find a JSON object or array with brace/bracket matching
    for search_text in [cleaned, inside_thinking]:
        if not search_text:
            continue
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = search_text.find(start_char)
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(search_text)):
                if search_text[i] == start_char:
                    depth += 1
                elif search_text[i] == end_char:
                    depth -= 1
                if depth == 0:
                    try:
                        return json.loads(search_text[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break

    return {}


# ──────────────────────────────────────────────────────────────
# Tool Execution Loop
# ──────────────────────────────────────────────────────────────

async def run_tool_agent(
    llm: ChatNVIDIA,
    tools: list[Any],
    system_prompt: str,
    user_message: str,
    max_iterations: int = 5,
) -> str:
    """
    Run an LLM with tools in a loop until it produces a final text response.

    This implements the standard LangChain tool-calling pattern:
    1. Invoke LLM with tools bound
    2. If response contains tool_calls, execute each tool
    3. Feed ToolMessages back and re-invoke
    4. Repeat until LLM returns text (no tool_calls) or max iterations hit

    Returns the final text content from the LLM.
    """
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    messages: list[Any] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    for iteration in range(max_iterations):
        await rate_limit_wait()
        try:
            response: AIMessage = await llm_with_tools.ainvoke(messages)
        except Exception as exc:
            print(f"  [tool_agent] iter {iteration+1}: LLM error: {type(exc).__name__}: {exc}")
            break
        messages.append(response)

        if not response.tool_calls:
            content = _extract_content(response)
            print(f"  [tool_agent] iter {iteration+1}: final text ({len(content)} chars)")
            return content

        print(f"  [tool_agent] iter {iteration+1}: {len(response.tool_calls)} tool call(s): "
              f"{[tc['name'] for tc in response.tool_calls]}")

        for tc in response.tool_calls:
            tool_fn = tools_by_name.get(tc["name"])
            if tool_fn is None:
                result = json.dumps({"error": f"Unknown tool: {tc['name']}"})
            else:
                try:
                    raw = tool_fn.invoke(tc["args"])
                    result = json.dumps(raw) if not isinstance(raw, str) else raw
                except Exception as exc:
                    result = json.dumps({"error": str(exc)})
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

    print(f"  [tool_agent] exhausted {max_iterations} iterations")
    last_ai = [m for m in messages if isinstance(m, AIMessage)]
    return _extract_content(last_ai[-1]) if last_ai else ""


def _extract_content(msg: AIMessage) -> str:
    """Extract text content from an AIMessage, handling list-type content."""
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return " ".join(parts)
    return str(content)
