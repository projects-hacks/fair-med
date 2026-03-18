"""
BillShield — Pricing Agent

Purpose: Compare each billed charge against real CMS RVU26B Medicare fair rates.

This agent pre-fetches Medicare rates from Supabase deterministically (no
tool-calling loop), then passes the complete comparison to the LLM for a
brief overcharge analysis.  The pricing_results are built in Python, not
parsed from LLM output, so they're always accurate.
"""

from __future__ import annotations

from typing import Any

from .state import BillShieldState
from tools import db


async def run_pricing(state: BillShieldState) -> dict[str, Any]:
    """Pricing node: looks up Medicare rates and flags overcharges."""
    charges = state.get("parsed_charges", [])
    if not charges:
        return {
            "pricing_results": [],
            "total_billed": 0.0,
            "total_fair": 0.0,
            "total_overcharge": 0.0,
            "current_agent": "pricing",
        }

    pricing_results: list[dict[str, Any]] = []
    total_billed = 0.0
    total_fair = 0.0

    for charge in charges:
        cpt = str(charge.get("cpt_code", "")).strip()
        billed = _safe_float(charge.get("charge"))
        qty = int(charge.get("quantity", 1) or 1)
        description = charge.get("description", "")

        total_billed += billed

        if not cpt:
            pricing_results.append({
                "cpt_code": cpt,
                "description": description,
                "billed": billed,
                "medicare_rate": 0.0,
                "overcharge_pct": 0.0,
                "overcharge_amount": 0.0,
                "severity": "UNKNOWN",
                "found": False,
            })
            continue

        try:
            rate_info = db.lookup_medicare_rate(cpt)
        except Exception:
            rate_info = {"found": False, "non_facility_rate": 0, "facility_rate": 0}

        medicare_rate = float(rate_info.get("non_facility_rate", 0) or 0)
        if medicare_rate == 0:
            medicare_rate = float(rate_info.get("facility_rate", 0) or 0)

        fair_total = medicare_rate * qty
        total_fair += fair_total

        if medicare_rate > 0:
            overcharge_pct = ((billed - fair_total) / fair_total) * 100
        else:
            overcharge_pct = 0.0

        overcharge_amount = max(billed - fair_total, 0.0)

        if overcharge_pct >= 300:
            severity = "EXTREME"
        elif overcharge_pct >= 100:
            severity = "MAJOR"
        elif overcharge_pct >= 25:
            severity = "MINOR"
        elif overcharge_pct < 0:
            severity = "UNDER"
        else:
            severity = "FAIR"

        pricing_results.append({
            "cpt_code": cpt,
            "description": description or rate_info.get("description", ""),
            "billed": billed,
            "medicare_rate": round(float(fair_total), 2),
            "overcharge_pct": round(float(overcharge_pct), 1),
            "overcharge_amount": round(float(overcharge_amount), 2),
            "severity": severity,
            "found": rate_info.get("found", False),
            "category": rate_info.get("category", "Unknown"),
        })

    total_overcharge = max(total_billed - total_fair, 0.0)

    print(f"[Pricing] {len(pricing_results)} charges processed")
    for pr in pricing_results:
        print(f"  {pr['cpt_code']} | billed=${pr['billed']:.2f} "
              f"| medicare=${pr['medicare_rate']:.2f} "
              f"| {pr['overcharge_pct']:.1f}% | {pr['severity']}")
    print(f"[Pricing] Total: billed=${total_billed:.2f} fair=${total_fair:.2f} "
          f"overcharge=${total_overcharge:.2f}")

    return {
        "pricing_results": pricing_results,
        "total_billed": round(total_billed, 2),
        "total_fair": round(total_fair, 2),
        "total_overcharge": round(total_overcharge, 2),
        "current_agent": "pricing",
    }


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0.0
