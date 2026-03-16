"""
Medicare pricing tool for BillShield.

This exposes the existing Supabase-backed lookup_medicare_rate helper
from tools.db as a LangChain tool for use by the Pricing agent.
"""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.tools import tool

from . import db


@tool
def lookup_medicare_rate(cpt_code: str, modifier: str = "", program_type: str = "non_qpp") -> Dict[str, Any]:
    """
    Look up the Medicare fair payment rate for a CPT/HCPCS code.

    Args:
        cpt_code: CPT or HCPCS code, e.g. "99213" or "36415".
        modifier: Optional modifier (e.g. "25"). Defaults to empty string.
        program_type: "non_qpp" (default) or "qpp".

    Returns:
        A JSON-serializable dict with:
        - cpt_code, modifier, description, category
        - facility_rate, non_facility_rate
        - computed_* and published_* rates when available
        - program_type, effective_year
        - found: bool indicating whether a rate was found

    Notes:
        This uses the real CMS RVU26B data loaded into Supabase
        (cms_pfs_rvu table) and falls back to the legacy medicare_rates
        table if necessary.
    """
    normalized = (cpt_code or "").strip().upper()
    if not normalized:
        return {
            "cpt_code": cpt_code,
            "modifier": modifier,
            "description": "Unknown",
            "category": "Unknown",
            "facility_rate": 0.0,
            "non_facility_rate": 0.0,
            "computed_facility_rate": 0.0,
            "computed_non_facility_rate": 0.0,
            "published_facility_rate": 0.0,
            "published_non_facility_rate": 0.0,
            "program_type": program_type,
            "effective_year": 2026,
            "found": False,
        }

    try:
        result = db.lookup_medicare_rate(
            cpt_code=normalized,
            modifier=modifier or "",
            program_type=program_type or "non_qpp",
        )
        # Ensure the result is JSON-serializable and includes a 'found' flag.
        if not isinstance(result, dict):
            return {
                "cpt_code": normalized,
                "modifier": modifier,
                "description": "Unknown",
                "category": "Unknown",
                "facility_rate": 0.0,
                "non_facility_rate": 0.0,
                "computed_facility_rate": 0.0,
                "computed_non_facility_rate": 0.0,
                "published_facility_rate": 0.0,
                "published_non_facility_rate": 0.0,
                "program_type": program_type,
                "effective_year": 2026,
                "found": False,
            }

        # Backfill 'found' if db.lookup_medicare_rate didn't set it.
        if "found" not in result:
            found = bool(result.get("facility_rate") or result.get("non_facility_rate"))
            result = {**result, "found": found}

        # Normalise fields for downstream agents.
        safe: Dict[str, Any] = {
            "cpt_code": result.get("cpt_code", normalized),
            "modifier": result.get("modifier", modifier or ""),
            "description": result.get("description", "Unknown"),
            "category": result.get("category", "Unknown"),
            "facility_rate": float(result.get("facility_rate", 0.0) or 0.0),
            "non_facility_rate": float(result.get("non_facility_rate", 0.0) or 0.0),
            "computed_facility_rate": float(result.get("computed_facility_rate", 0.0) or 0.0),
            "computed_non_facility_rate": float(result.get("computed_non_facility_rate", 0.0) or 0.0),
            "published_facility_rate": float(result.get("published_facility_rate", 0.0) or 0.0),
            "published_non_facility_rate": float(result.get("published_non_facility_rate", 0.0) or 0.0),
            "program_type": result.get("program_type", program_type or "non_qpp"),
            "effective_year": int(result.get("effective_year", 2026) or 2026),
            "found": bool(result.get("found", False)),
        }
        return safe
    except Exception as exc:  # noqa: BLE001
        return {
            "cpt_code": normalized,
            "modifier": modifier,
            "description": "Unknown",
            "category": "Unknown",
            "facility_rate": 0.0,
            "non_facility_rate": 0.0,
            "computed_facility_rate": 0.0,
            "computed_non_facility_rate": 0.0,
            "published_facility_rate": 0.0,
            "published_non_facility_rate": 0.0,
            "program_type": program_type,
            "effective_year": 2026,
            "found": False,
            "error": str(exc),
        }

