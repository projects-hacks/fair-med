"""
Web search tool for BillShield.

This wraps DuckDuckGo search in a LangChain tool so the Researcher
agent can retrieve up-to-date patient rights and billing protections.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.tools import tool


def _run_ddg_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Execute a DuckDuckGo search and return a normalized result list.

    Uses the ``ddgs`` package (successor to duckduckgo_search).
    Falls back to the legacy package only if ddgs is not installed.
    """
    try:
        from ddgs import DDGS  # type: ignore[import-not-found]
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore[import-not-found]
        except ImportError:
            return []

    try:
        ddg = DDGS()
        results = list(ddg.text(query, max_results=max_results))
    except Exception:  # noqa: BLE001
        return []

    normalized: List[Dict[str, Any]] = []
    for item in results:
        title = item.get("title") or ""
        href = item.get("href") or item.get("url") or ""
        snippet = item.get("body") or item.get("description") or ""
        normalized.append(
            {
                "title": title,
                "url": href,
                "snippet": snippet,
            }
        )
    return normalized


@tool
def search_patient_rights(query: str) -> Dict[str, Any]:
    """
    Search for medical billing / patient rights information.

    Args:
        query: Research question, e.g. "No Surprises Act emergency services protections".

    Returns:
        Dict with:
        - query: the original query
        - results: list of {title, url, snippet}
        - fallback_used: bool indicating whether static fallback content was used
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return {
            "query": query,
            "results": [],
            "fallback_used": False,
        }

    results = _run_ddg_search(cleaned, max_results=5)
    if results:
        return {
            "query": cleaned,
            "results": results,
            "fallback_used": False,
        }

    # Fallback: curated baseline rights, so the Researcher agent always has something.
    fallback_results: List[Dict[str, Any]] = [
        {
            "title": "No Surprises Act — Protections Against Surprise Medical Bills",
            "url": "https://www.cms.gov/nosurprises",
            "snippet": (
                "Federal law that protects patients from surprise out-of-network bills "
                "for emergency services and certain non-emergency services at in-network facilities."
            ),
        },
        {
            "title": "California Fair Billing Act — Hospital Billing Protections",
            "url": "https://oag.ca.gov/consumers/general/medical-billing",
            "snippet": (
                "State protections that limit what hospitals may bill uninsured and underinsured "
                "patients and require financial assistance policies."
            ),
        },
    ]
    return {
        "query": cleaned,
        "results": fallback_results,
        "fallback_used": True,
    }

