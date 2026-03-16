"""
Billing rules tool for BillShield.

Exposes NCCI PTP unbundling edits, MUE limits, and heuristic rules
from the Supabase billing_rules table as LangChain tools.
All data comes from real CMS NCCI quarterly releases loaded via
load_billing_rules.py — no synthetic data.
"""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.tools import tool

from . import db


@tool
def check_billing_rules(cpt_codes: List[str]) -> Dict[str, Any]:
    """
    Fetch all billing rules relevant to a set of CPT codes from the database.

    This queries the Supabase billing_rules table which contains real CMS
    NCCI data: PTP unbundling edits, MUE limits, duplicate detection rules,
    upcoding rules, and overcharge thresholds.

    Args:
        cpt_codes: List of CPT/HCPCS codes from the bill, e.g. ["99215", "80053", "80048"]

    Returns:
        A dict grouped by rule_type with only rules matching the given codes:
        {
            "duplicate": [...],       # rules for detecting duplicate charges
            "upcoding": [...],        # E/M level vs diagnosis complexity rules
            "unbundling": [...],      # NCCI PTP edit pairs that cannot be billed together
            "mue": [...],             # Medically Unlikely Edits (max units per service)
            "overcharge": [...],      # Overcharge threshold definitions
            "meta": {
                "total_rules_found": 15,
                "codes_queried": ["99215", "80053", "80048"],
                "source": "CMS NCCI quarterly + CMS E/M guidance via Supabase"
            }
        }
    """
    codes = [c.strip().upper() for c in cpt_codes if c and c.strip()]
    if not codes:
        return {
            "meta": {
                "total_rules_found": 0,
                "codes_queried": [],
                "source": "No codes provided",
            }
        }

    try:
        rules = db.get_rules_for_bill(codes)
    except Exception as exc:
        return {
            "error": str(exc),
            "meta": {
                "total_rules_found": 0,
                "codes_queried": codes,
                "source": "Supabase query failed",
            }
        }

    total = sum(len(v) for v in rules.values())
    rules["meta"] = {
        "total_rules_found": total,
        "codes_queried": codes,
        "source": "CMS NCCI quarterly + CMS E/M guidance via Supabase",
    }
    return rules


@tool
def get_ncci_unbundling_pairs(cpt_codes: List[str]) -> Dict[str, Any]:
    """
    Check if any pair of CPT codes violates NCCI PTP (Procedure-to-Procedure) edits.

    NCCI PTP edits define code pairs that should NOT be billed together
    on the same date of service. This queries real CMS NCCI quarterly data.

    Args:
        cpt_codes: List of CPT codes to check for unbundling conflicts,
                   e.g. ["80048", "80053"]

    Returns:
        {
            "pairs_found": 3,
            "unbundling_rules": [
                {
                    "rule_name": "NCCI PTP practitioner: 80048 + 80053",
                    "severity": "HIGH",
                    "description": "NCCI PTP addition pair with modifier indicator 0.",
                    "trigger_codes": {"cpt_codes": ["80048", "80053"], ...},
                    "condition": {"check": "codes_billed_together", ...}
                }
            ]
        }
    """
    codes = [c.strip().upper() for c in cpt_codes if c and c.strip()]
    if not codes:
        return {"pairs_found": 0, "unbundling_rules": []}

    try:
        rules = db.get_ncci_ptp_pairs_for_codes(codes)
    except Exception as exc:
        return {"pairs_found": 0, "unbundling_rules": [], "error": str(exc)}

    return {
        "pairs_found": len(rules),
        "unbundling_rules": rules,
    }


@tool
def get_mue_limits(cpt_codes: List[str]) -> Dict[str, Any]:
    """
    Get Medically Unlikely Edits (MUE) unit limits for specific CPT codes.

    MUE values define the maximum units of service a provider would report
    for a single beneficiary on a single date of service. Exceeding the MUE
    limit suggests a billing error.

    Args:
        cpt_codes: List of CPT codes to check MUE limits for,
                   e.g. ["99213", "36415"]

    Returns:
        {
            "limits_found": 2,
            "mue_rules": [
                {
                    "rule_name": "MUE Limit practitioner: 99213 <= 1",
                    "condition": {"max_units": 1, "adjudication_indicator": "2", ...},
                    ...
                }
            ]
        }
    """
    codes = [c.strip().upper() for c in cpt_codes if c and c.strip()]
    if not codes:
        return {"limits_found": 0, "mue_rules": []}

    try:
        rules = db.get_mue_limits_for_codes(codes)
    except Exception as exc:
        return {"limits_found": 0, "mue_rules": [], "error": str(exc)}

    return {
        "limits_found": len(rules),
        "mue_rules": rules,
    }
