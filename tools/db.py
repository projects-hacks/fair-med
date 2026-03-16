"""
BillShield — Supabase Database Client

Provides helper functions for agents to query Supabase.
All agents use these functions instead of reading local JSON files.
"""

import os
import json
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    """Get or create the Supabase client (singleton)."""
    global _client
    if _client is None:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


# ──────────────────────────────────────────────────────────────
# Medicare Rates Queries (used by Pricing agent)
# ──────────────────────────────────────────────────────────────

def _format_rate_row(cpt_code: str, row: dict) -> dict:
    published_facility = row.get("published_facility_rate")
    published_nonfacility = row.get("published_nonfacility_rate")
    computed_facility = row.get("computed_facility_rate")
    computed_nonfacility = row.get("computed_nonfacility_rate")

    # Use published rate only if it's a real positive value; otherwise fall back to computed
    facility_rate = published_facility if published_facility else computed_facility
    non_facility_rate = published_nonfacility if published_nonfacility else computed_nonfacility

    return {
        "cpt_code": row.get("hcpcs", cpt_code),
        "modifier": row.get("modifier", ""),
        "description": row.get("description", "Unknown"),
        "category": get_category_for_code(row.get("hcpcs", cpt_code)),
        "facility_rate": float(facility_rate or 0),
        "non_facility_rate": float(non_facility_rate or 0),
        "computed_facility_rate": float(computed_facility or 0),
        "computed_non_facility_rate": float(computed_nonfacility or 0),
        "published_facility_rate": float(published_facility or 0),
        "published_non_facility_rate": float(published_nonfacility or 0),
        "program_type": row.get("program_type", "non_qpp"),
        "effective_year": row.get("effective_year", 2026),
        "found": True,
    }


def get_category_for_code(cpt_code: str) -> str:
    code = cpt_code.strip()
    if not code.isdigit():
        return "Other"
    c = int(code)
    if 99201 <= c <= 99499:
        return "E&M"
    if 80000 <= c <= 89999:
        return "Lab"
    if 70000 <= c <= 79999:
        return "Imaging"
    if 10000 <= c <= 69999:
        return "Surgery"
    if 90000 <= c <= 96999:
        return "Vaccine"
    if 96000 <= c <= 99199:
        return "Procedure"
    return "Other"


def lookup_medicare_rate(cpt_code: str, modifier: str = "", program_type: str = "non_qpp") -> dict:
    """
    Look up the Medicare fair payment rate for a CPT code.

    Returns:
        {
            "cpt_code": "99213",
            "description": "Office visit, est patient, low complexity",
            "category": "E&M",
            "facility_rate": 78.11,
            "non_facility_rate": 110.35,
            "found": True
        }
    """
    client = get_client()
    code = cpt_code.strip()
    mod = modifier.strip().upper()

    try:
        query = (
            client.table("cms_pfs_rvu")
            .select("*")
            .eq("hcpcs", code)
            .eq("effective_year", 2026)
            .eq("release_tag", "apr_2026")
            .eq("program_type", program_type)
        )
        if mod:
            query = query.eq("modifier", mod)
        else:
            query = query.eq("modifier", "")

        result = query.limit(1).execute()
        if result.data:
            return _format_rate_row(code, result.data[0])
    except Exception:
        pass

    result = client.table("medicare_rates").select("*").eq("cpt_code", code).execute()
    if result.data:
        row = result.data[0]
        return {
            "cpt_code": row["cpt_code"],
            "modifier": "",
            "description": row["description"],
            "category": row["category"],
            "facility_rate": float(row["facility_rate"]),
            "non_facility_rate": float(row["non_facility_rate"]),
            "computed_facility_rate": float(row["facility_rate"]),
            "computed_non_facility_rate": float(row["non_facility_rate"]),
            "published_facility_rate": float(row["facility_rate"]),
            "published_non_facility_rate": float(row["non_facility_rate"]),
            "program_type": "legacy",
            "effective_year": row.get("effective_year", 2026),
            "found": True,
        }

    return {
        "cpt_code": cpt_code,
        "modifier": mod,
        "description": "Unknown",
        "category": "Unknown",
        "facility_rate": 0,
        "non_facility_rate": 0,
        "computed_facility_rate": 0,
        "computed_non_facility_rate": 0,
        "published_facility_rate": 0,
        "published_non_facility_rate": 0,
        "program_type": program_type,
        "effective_year": 2026,
        "found": False,
    }


def lookup_multiple_rates(cpt_codes: list[str], program_type: str = "non_qpp") -> list[dict]:
    """Look up Medicare rates for multiple CPT codes in one query."""
    return [lookup_medicare_rate(code, program_type=program_type) for code in cpt_codes]


# ──────────────────────────────────────────────────────────────
# Billing Rules Queries (used by Auditor agent)
# ──────────────────────────────────────────────────────────────

def _parse_rule_row(row: dict) -> dict:
    """Normalise a billing_rules row from Supabase."""
    tc = row.get("trigger_codes")
    cond = row.get("condition")
    return {
        "id": row["id"],
        "rule_type": row["rule_type"],
        "rule_name": row["rule_name"],
        "severity": row["severity"],
        "description": row["description"],
        "trigger_codes": tc if isinstance(tc, dict) else json.loads(tc) if tc else None,
        "condition": cond if isinstance(cond, dict) else json.loads(cond) if cond else None,
        "source": row.get("source", ""),
    }


def get_billing_rules(rule_type: str = None) -> list[dict]:
    """
    Get active billing rules, optionally filtered by type.

    Args:
        rule_type: 'duplicate', 'upcoding', 'unbundling', 'overcharge', 'mue', or None for all
    """
    client = get_client()
    query = client.table("billing_rules").select("*").eq("is_active", True)
    if rule_type:
        query = query.eq("rule_type", rule_type)
    result = query.execute()
    return [_parse_rule_row(row) for row in (result.data or [])]


def get_all_billing_rules() -> dict:
    """Get all active billing rules grouped by type."""
    rules = get_billing_rules()
    grouped: dict[str, list[dict]] = {}
    for rule in rules:
        grouped.setdefault(rule["rule_type"], []).append(rule)
    return grouped


def get_ncci_ptp_pairs_for_codes(cpt_codes: list[str]) -> list[dict]:
    """
    Query NCCI PTP unbundling pairs that involve ANY of the given CPT codes.

    PTP rule_names follow the pattern "NCCI PTP practitioner: CODE1 + CODE2",
    so we search via rule_name with ilike. We also load ALL heuristic
    (non-NCCI) unbundling rules since they're few (~2-3) and always relevant.
    """
    if not cpt_codes:
        return []

    client = get_client()
    seen_ids: set[int] = set()
    results: list[dict] = []

    # 1. Load heuristic unbundling rules (small set, always relevant)
    try:
        heuristic = (
            client.table("billing_rules")
            .select("*")
            .eq("is_active", True)
            .eq("rule_type", "unbundling")
            .not_.ilike("rule_name", "NCCI PTP%")
            .execute()
        )
        for row in (heuristic.data or []):
            seen_ids.add(row.get("id"))
            results.append(_parse_rule_row(row))
    except Exception:
        pass

    # 2. Search NCCI PTP rules by code in rule_name
    for code in cpt_codes:
        code = code.strip()
        if not code:
            continue
        try:
            resp = (
                client.table("billing_rules")
                .select("*")
                .eq("is_active", True)
                .eq("rule_type", "unbundling")
                .ilike("rule_name", f"NCCI PTP%{code}%")
                .execute()
            )
            for row in (resp.data or []):
                rid = row.get("id")
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    results.append(_parse_rule_row(row))
        except Exception:
            continue

    return results


def get_mue_limits_for_codes(cpt_codes: list[str]) -> list[dict]:
    """
    Query MUE (Medically Unlikely Edits) limits for specific CPT codes.

    MUE rule_names follow "MUE Limit practitioner: CODE <= N",
    so we search via rule_name with or_ filter.
    """
    if not cpt_codes:
        return []

    client = get_client()
    results: list[dict] = []

    # Build an OR filter: rule_name.ilike.%CODE1%,rule_name.ilike.%CODE2%,...
    # Process in batches to avoid overly long filter strings
    codes = [c.strip() for c in cpt_codes if c.strip()]
    if not codes:
        return []

    or_clauses = ",".join(f"rule_name.ilike.%{code}%" for code in codes)

    try:
        resp = (
            client.table("billing_rules")
            .select("*")
            .eq("is_active", True)
            .eq("rule_type", "mue")
            .or_(or_clauses)
            .execute()
        )
        for row in (resp.data or []):
            results.append(_parse_rule_row(row))
    except Exception:
        pass

    return results


def get_rules_for_bill(cpt_codes: list[str]) -> dict:
    """
    One-stop query: fetch ALL billing rules relevant to a specific bill.

    Returns a dict grouped by rule_type with only the rules that match
    the CPT codes in the bill.  This is the primary entry point for the
    Auditor agent.
    """
    result: dict[str, list[dict]] = {}

    # Heuristic rules (always relevant — small, <10 rows)
    for rule_type in ("duplicate", "upcoding", "overcharge"):
        rows = get_billing_rules(rule_type=rule_type)
        if rows:
            result[rule_type] = rows

    # NCCI PTP unbundling pairs filtered to this bill's codes
    ptp = get_ncci_ptp_pairs_for_codes(cpt_codes)
    if ptp:
        result["unbundling"] = ptp

    # MUE limits filtered to this bill's codes
    mue = get_mue_limits_for_codes(cpt_codes)
    if mue:
        result["mue"] = mue

    return result


# ──────────────────────────────────────────────────────────────
# Sample Bills Queries (used by Streamlit UI)
# ──────────────────────────────────────────────────────────────

def get_sample_bills() -> list[dict]:
    """Get all demo bills for the UI."""
    client = get_client()
    result = client.table("sample_bills").select("*").eq("is_demo", True).order("difficulty").execute()
    return result.data


def get_sample_bill(bill_id: str) -> dict | None:
    """Get a specific sample bill by ID."""
    client = get_client()
    result = client.table("sample_bills").select("*").eq("bill_id", bill_id).execute()
    return result.data[0] if result.data else None


# ──────────────────────────────────────────────────────────────
# Analysis Results (used by graph + UI)
# ──────────────────────────────────────────────────────────────

def create_analysis(bill_text: str) -> str:
    """Create a new analysis record. Returns the session_id."""
    client = get_client()
    result = client.table("analysis_results").insert({
        "bill_text": bill_text,
        "status": "pending",
    }).execute()
    return result.data[0]["session_id"]


def update_analysis(session_id: str, updates: dict):
    """Update an analysis record with agent outputs."""
    client = get_client()
    # Convert any dicts/lists in updates to JSON strings for JSONB columns
    jsonb_columns = [
        "parsed_charges", "icd_codes", "pricing_analysis",
        "audit_findings", "research_findings", "verified_rights", "agents_used"
    ]
    for col in jsonb_columns:
        if col in updates and isinstance(updates[col], (dict, list)):
            updates[col] = json.dumps(updates[col])

    client.table("analysis_results").update(updates).eq("session_id", session_id).execute()


def complete_analysis(session_id: str, summary_data: dict):
    """Mark analysis as complete with final metrics."""
    updates = {
        "status": "complete",
        "completed_at": "now()",
        **summary_data,
    }
    update_analysis(session_id, updates)


def get_recent_analyses(limit: int = 10) -> list[dict]:
    """Get recent completed analyses for the UI dashboard."""
    client = get_client()
    result = (
        client.table("analysis_results")
        .select("session_id, total_billed, total_overcharge, errors_found, processing_time_ms, created_at")
        .eq("status", "complete")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
