#!/usr/bin/env python3
"""
BillShield — Supabase Setup & Data Loading Script

Steps:
    1. Create Supabase project at https://supabase.com
    2. Add SUPABASE_URL and SUPABASE_KEY to .env
    3. Run: python load_supabase.py --schema   (prints SQL to paste into SQL Editor)
    4. Paste and execute the SQL in Supabase Dashboard → SQL Editor
    5. Run: python load_supabase.py             (loads all data)
    6. Run: python load_supabase.py --verify    (checks data loaded correctly)
"""

import os
import json
import sys
from typing import Any, cast
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────
# COMPLETE SQL SCHEMA
# ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- =============================================
-- BILLSHIELD SUPABASE SCHEMA
-- Run in: Supabase Dashboard → SQL Editor → New Query
-- =============================================

-- 1. Medicare Rates (CMS Physician Fee Schedule data)
CREATE TABLE IF NOT EXISTS medicare_rates (
    id              BIGSERIAL PRIMARY KEY,
    cpt_code        VARCHAR(10) NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    category        VARCHAR(50) NOT NULL,       -- 'E&M', 'Lab', 'Imaging', 'Surgery', 'Procedure', 'Vaccine', 'Other'
    facility_rate   DECIMAL(10,2) NOT NULL,
    non_facility_rate DECIMAL(10,2) NOT NULL,
    effective_year  INT NOT NULL DEFAULT 2026,
    source          VARCHAR(100) DEFAULT 'CMS PFS National',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_medicare_rates_cpt ON medicare_rates(cpt_code);
CREATE INDEX IF NOT EXISTS idx_medicare_rates_category ON medicare_rates(category);

-- 2. Billing Rules (error detection logic for Auditor agent)
CREATE TABLE IF NOT EXISTS billing_rules (
    id              BIGSERIAL PRIMARY KEY,
    rule_type       VARCHAR(30) NOT NULL,       -- 'duplicate', 'upcoding', 'unbundling', 'overcharge'
    rule_name       VARCHAR(200) NOT NULL,
    severity        VARCHAR(10) NOT NULL,       -- 'HIGH', 'MEDIUM', 'LOW'
    description     TEXT NOT NULL,
    trigger_codes   JSONB,                      -- CPT/ICD codes that activate this rule
    condition       JSONB,                      -- structured condition logic
    source          VARCHAR(100) DEFAULT 'CMS/NCCI',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_billing_rules_type ON billing_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_billing_rules_active ON billing_rules(is_active);

-- 3. Sample Bills (pre-built demo data)
CREATE TABLE IF NOT EXISTS sample_bills (
    id              BIGSERIAL PRIMARY KEY,
    bill_id         VARCHAR(50) NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    bill_text       TEXT NOT NULL,
    difficulty      VARCHAR(20) DEFAULT 'medium',  -- 'easy', 'medium', 'hard'
    expected_errors JSONB,
    estimated_savings_low   DECIMAL(10,2),
    estimated_savings_high  DECIMAL(10,2),
    is_demo         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Analysis Results (full pipeline output — every agent writes here)
CREATE TABLE IF NOT EXISTS analysis_results (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID NOT NULL DEFAULT gen_random_uuid(),
    bill_text           TEXT NOT NULL,

    -- Agent outputs
    parsed_charges      JSONB,          -- from Parser agent
    icd_codes           JSONB,          -- from Parser agent
    pricing_analysis    JSONB,          -- from Pricing agent
    audit_findings      JSONB,          -- from Auditor agent
    research_findings   JSONB,          -- from Researcher agent
    verified_rights     JSONB,          -- from Fact-Checker agent
    dispute_letter      TEXT,           -- from Writer agent
    summary             TEXT,           -- from Writer agent

    -- Aggregated metrics
    total_billed        DECIMAL(10,2),
    total_fair_rate     DECIMAL(10,2),
    total_overcharge    DECIMAL(10,2),
    errors_found        INT DEFAULT 0,
    potential_savings_low  DECIMAL(10,2),
    potential_savings_high DECIMAL(10,2),

    -- Performance metadata
    agents_used         JSONB,          -- which agents ran + timing
    model_super_calls   INT DEFAULT 0,
    model_nano_calls    INT DEFAULT 0,
    processing_time_ms  INT,
    status              VARCHAR(30) DEFAULT 'pending',  -- 'pending', 'processing', 'complete', 'error'
    error_message       TEXT,

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_analysis_session ON analysis_results(session_id);
CREATE INDEX IF NOT EXISTS idx_analysis_status ON analysis_results(status);

-- 5. Row Level Security (allow public read, full access for analysis)
ALTER TABLE medicare_rates ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE sample_bills ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public_read_medicare_rates" ON medicare_rates;
DROP POLICY IF EXISTS "public_read_billing_rules" ON billing_rules;
DROP POLICY IF EXISTS "public_read_sample_bills" ON sample_bills;
DROP POLICY IF EXISTS "public_all_analysis_results" ON analysis_results;
DROP POLICY IF EXISTS "public_write_medicare_rates" ON medicare_rates;
DROP POLICY IF EXISTS "public_write_billing_rules" ON billing_rules;
DROP POLICY IF EXISTS "public_write_sample_bills" ON sample_bills;

CREATE POLICY "public_read_medicare_rates" ON medicare_rates FOR SELECT USING (true);
CREATE POLICY "public_read_billing_rules" ON billing_rules FOR SELECT USING (true);
CREATE POLICY "public_read_sample_bills" ON sample_bills FOR SELECT USING (true);
CREATE POLICY "public_all_analysis_results" ON analysis_results FOR ALL USING (true);

CREATE POLICY "public_write_medicare_rates" ON medicare_rates FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_billing_rules" ON billing_rules FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_sample_bills" ON sample_bills FOR ALL USING (true) WITH CHECK (true);

-- 6. CMS RVU26B load runs (provenance + idempotency metadata)
CREATE TABLE IF NOT EXISTS cms_load_runs (
    id                  BIGSERIAL PRIMARY KEY,
    dataset_name        VARCHAR(120) NOT NULL,
    source_file         VARCHAR(255) NOT NULL,
    file_sha256         VARCHAR(64),
    effective_year      INT NOT NULL,
    release_tag         VARCHAR(50) NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    status              VARCHAR(30) NOT NULL DEFAULT 'started',
    rows_parsed         INT NOT NULL DEFAULT 0,
    rows_loaded         INT NOT NULL DEFAULT 0,
    rows_rejected       INT NOT NULL DEFAULT 0,
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_cms_load_runs_dataset ON cms_load_runs(dataset_name);
CREATE INDEX IF NOT EXISTS idx_cms_load_runs_year ON cms_load_runs(effective_year);

-- 7. Row-level rejects for strict non-silent parsing
CREATE TABLE IF NOT EXISTS cms_row_rejects (
    id                  BIGSERIAL PRIMARY KEY,
    load_run_id         BIGINT REFERENCES cms_load_runs(id) ON DELETE CASCADE,
    dataset_name        VARCHAR(120) NOT NULL,
    source_file         VARCHAR(255) NOT NULL,
    row_number          INT,
    reject_reason       VARCHAR(120) NOT NULL,
    raw_row             JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cms_row_rejects_run ON cms_row_rejects(load_run_id);
CREATE INDEX IF NOT EXISTS idx_cms_row_rejects_dataset ON cms_row_rejects(dataset_name);

-- 8. Core PFS RVU records (PPRRVU non-QPP + QPP)
CREATE TABLE IF NOT EXISTS cms_pfs_rvu (
    id                          BIGSERIAL PRIMARY KEY,
    effective_year              INT NOT NULL,
    release_tag                 VARCHAR(50) NOT NULL,
    program_type                VARCHAR(20) NOT NULL, -- 'non_qpp' | 'qpp'
    hcpcs                       VARCHAR(10) NOT NULL,
    modifier                    VARCHAR(5) NOT NULL DEFAULT '',
    description                 TEXT NOT NULL,
    status_code                 VARCHAR(5),
    payment_indicator           VARCHAR(10),
    work_rvu                    DECIMAL(10,4),
    nonfacility_pe_rvu          DECIMAL(10,4),
    facility_pe_rvu             DECIMAL(10,4),
    malpractice_rvu             DECIMAL(10,4),
    nonfacility_total_rvu       DECIMAL(10,4),
    facility_total_rvu          DECIMAL(10,4),
    conversion_factor           DECIMAL(10,4),
    computed_nonfacility_rate   DECIMAL(12,4),
    computed_facility_rate      DECIMAL(12,4),
    published_nonfacility_rate  DECIMAL(12,4),
    published_facility_rate     DECIMAL(12,4),
    load_run_id                 BIGINT REFERENCES cms_load_runs(id) ON DELETE SET NULL,
    source_file                 VARCHAR(255) NOT NULL,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (effective_year, release_tag, program_type, hcpcs, modifier)
);

CREATE INDEX IF NOT EXISTS idx_cms_pfs_hcpcs ON cms_pfs_rvu(hcpcs);
CREATE INDEX IF NOT EXISTS idx_cms_pfs_program ON cms_pfs_rvu(program_type);
CREATE INDEX IF NOT EXISTS idx_cms_pfs_mod ON cms_pfs_rvu(modifier);

-- 9. GPCI locality factors
CREATE TABLE IF NOT EXISTS cms_gpci_locality (
    id                          BIGSERIAL PRIMARY KEY,
    effective_year              INT NOT NULL,
    contractor                  VARCHAR(10) NOT NULL,
    state_code                  VARCHAR(5) NOT NULL,
    locality_number             VARCHAR(10) NOT NULL,
    locality_name               TEXT NOT NULL,
    pw_gpci_without_floor       DECIMAL(8,4),
    pw_gpci_with_floor          DECIMAL(8,4),
    pe_gpci                     DECIMAL(8,4),
    mp_gpci                     DECIMAL(8,4),
    load_run_id                 BIGINT REFERENCES cms_load_runs(id) ON DELETE SET NULL,
    source_file                 VARCHAR(255) NOT NULL,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (effective_year, contractor, state_code, locality_number)
);

CREATE INDEX IF NOT EXISTS idx_cms_gpci_lookup ON cms_gpci_locality(contractor, locality_number);

-- 10. County/locality crosswalk from 26LOCCO
CREATE TABLE IF NOT EXISTS cms_locality_crosswalk (
    id                          BIGSERIAL PRIMARY KEY,
    effective_year              INT NOT NULL,
    contractor                  VARCHAR(10) NOT NULL,
    locality_number             VARCHAR(10) NOT NULL,
    state_name                  VARCHAR(80),
    fee_schedule_area           TEXT NOT NULL,
    counties_raw                TEXT,
    load_run_id                 BIGINT REFERENCES cms_load_runs(id) ON DELETE SET NULL,
    source_file                 VARCHAR(255) NOT NULL,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (effective_year, contractor, locality_number, fee_schedule_area)
);

CREATE INDEX IF NOT EXISTS idx_cms_locality_crosswalk_lookup ON cms_locality_crosswalk(contractor, locality_number);

-- 11. Anesthesia conversion factors by locality
CREATE TABLE IF NOT EXISTS cms_anes_cf (
    id                          BIGSERIAL PRIMARY KEY,
    effective_year              INT NOT NULL,
    contractor                  VARCHAR(10) NOT NULL,
    locality_number             VARCHAR(10) NOT NULL,
    locality_name               TEXT NOT NULL,
    qpp_anes_cf                 DECIMAL(10,4),
    non_qpp_anes_cf             DECIMAL(10,4),
    load_run_id                 BIGINT REFERENCES cms_load_runs(id) ON DELETE SET NULL,
    source_file                 VARCHAR(255) NOT NULL,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (effective_year, contractor, locality_number)
);

CREATE INDEX IF NOT EXISTS idx_cms_anes_lookup ON cms_anes_cf(contractor, locality_number);

-- 12. OPPS cap locality pricing
CREATE TABLE IF NOT EXISTS cms_oppscap_pricing (
    id                          BIGSERIAL PRIMARY KEY,
    effective_year              INT NOT NULL,
    release_tag                 VARCHAR(50) NOT NULL,
    hcpcs                       VARCHAR(10) NOT NULL,
    modifier                    VARCHAR(5) NOT NULL DEFAULT '',
    procstat                    VARCHAR(5),
    contractor                  VARCHAR(10) NOT NULL,
    locality_number             VARCHAR(10) NOT NULL,
    facility_price              DECIMAL(12,4),
    nonfacility_price           DECIMAL(12,4),
    load_run_id                 BIGINT REFERENCES cms_load_runs(id) ON DELETE SET NULL,
    source_file                 VARCHAR(255) NOT NULL,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (effective_year, release_tag, hcpcs, modifier, contractor, locality_number)
);

CREATE INDEX IF NOT EXISTS idx_cms_oppscap_lookup ON cms_oppscap_pricing(hcpcs, contractor, locality_number);

ALTER TABLE cms_load_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_row_rejects ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_pfs_rvu ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_gpci_locality ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_locality_crosswalk ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_anes_cf ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_oppscap_pricing ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public_read_cms_load_runs" ON cms_load_runs;
DROP POLICY IF EXISTS "public_read_cms_row_rejects" ON cms_row_rejects;
DROP POLICY IF EXISTS "public_read_cms_pfs_rvu" ON cms_pfs_rvu;
DROP POLICY IF EXISTS "public_read_cms_gpci_locality" ON cms_gpci_locality;
DROP POLICY IF EXISTS "public_read_cms_locality_crosswalk" ON cms_locality_crosswalk;
DROP POLICY IF EXISTS "public_read_cms_anes_cf" ON cms_anes_cf;
DROP POLICY IF EXISTS "public_read_cms_oppscap_pricing" ON cms_oppscap_pricing;
DROP POLICY IF EXISTS "public_write_cms_load_runs" ON cms_load_runs;
DROP POLICY IF EXISTS "public_write_cms_row_rejects" ON cms_row_rejects;
DROP POLICY IF EXISTS "public_write_cms_pfs_rvu" ON cms_pfs_rvu;
DROP POLICY IF EXISTS "public_write_cms_gpci_locality" ON cms_gpci_locality;
DROP POLICY IF EXISTS "public_write_cms_locality_crosswalk" ON cms_locality_crosswalk;
DROP POLICY IF EXISTS "public_write_cms_anes_cf" ON cms_anes_cf;
DROP POLICY IF EXISTS "public_write_cms_oppscap_pricing" ON cms_oppscap_pricing;

CREATE POLICY "public_read_cms_load_runs" ON cms_load_runs FOR SELECT USING (true);
CREATE POLICY "public_read_cms_row_rejects" ON cms_row_rejects FOR SELECT USING (true);
CREATE POLICY "public_read_cms_pfs_rvu" ON cms_pfs_rvu FOR SELECT USING (true);
CREATE POLICY "public_read_cms_gpci_locality" ON cms_gpci_locality FOR SELECT USING (true);
CREATE POLICY "public_read_cms_locality_crosswalk" ON cms_locality_crosswalk FOR SELECT USING (true);
CREATE POLICY "public_read_cms_anes_cf" ON cms_anes_cf FOR SELECT USING (true);
CREATE POLICY "public_read_cms_oppscap_pricing" ON cms_oppscap_pricing FOR SELECT USING (true);

CREATE POLICY "public_write_cms_load_runs" ON cms_load_runs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_cms_row_rejects" ON cms_row_rejects FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_cms_pfs_rvu" ON cms_pfs_rvu FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_cms_gpci_locality" ON cms_gpci_locality FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_cms_locality_crosswalk" ON cms_locality_crosswalk FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_cms_anes_cf" ON cms_anes_cf FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public_write_cms_oppscap_pricing" ON cms_oppscap_pricing FOR ALL USING (true) WITH CHECK (true);
"""


# ──────────────────────────────────────────────────────────────
# CPT Code → Category Mapping
# ──────────────────────────────────────────────────────────────

def get_category(cpt_code: str) -> str:
    """Map a CPT code to its category."""
    code = cpt_code.strip()
    c = int(code) if code.isdigit() else 0

    if 99201 <= c <= 99499:
        return "E&M"
    elif 80000 <= c <= 89999:
        return "Lab"
    elif 70000 <= c <= 79999:
        return "Imaging"
    elif 10000 <= c <= 69999:
        return "Surgery"
    elif 90000 <= c <= 96999:
        return "Vaccine"
    elif 96000 <= c <= 99199:
        return "Procedure"
    else:
        return "Other"


# ──────────────────────────────────────────────────────────────
# Supabase Client
# ──────────────────────────────────────────────────────────────

def get_supabase_client() -> Any:
    """Initialize the Supabase client."""
    try:
        from supabase import create_client
    except ImportError:
        print("❌ supabase not installed. Run: pip install supabase")
        sys.exit(1)

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env")
        print("   Add to your .env file:")
        print("   SUPABASE_URL=https://xxxxx.supabase.co")
        print("   SUPABASE_KEY=eyJhbGciOi...")
        sys.exit(1)

    return create_client(url, key)


# ──────────────────────────────────────────────────────────────
# Data Loaders
# ──────────────────────────────────────────────────────────────

def load_medicare_rates(client: Any) -> int:
    """Load medicare_rates.json into Supabase."""
    print("\n📥 Loading medicare rates...")

    with open("data/medicare_rates.json", "r") as f:
        rates = cast(dict[str, dict[str, Any]], json.load(f))

    rows: list[dict[str, Any]] = []
    for cpt_code, data in rates.items():
        rows.append({
            "cpt_code": cpt_code,
            "description": data["description"],
            "category": get_category(cpt_code),
            "facility_rate": data["facility_rate"],
            "non_facility_rate": data["non_facility_rate"],
            "effective_year": 2026,
            "source": "CMS PFS National",
        })

    # Upsert in batches
    for i in range(0, len(rows), 50):
        batch = rows[i:i+50]
        client.table("medicare_rates").upsert(batch, on_conflict="cpt_code").execute()

    print(f"   ✅ Loaded {len(rows)} CPT codes")

    # Print category breakdown
    cats: dict[str, int] = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    for cat, count in sorted(cats.items()):
        print(f"      {cat}: {count} codes")

    return len(rows)


def load_billing_rules(client):
    """Load billing_rules.json into Supabase."""
    print("\n📥 Loading billing rules...")

    with open("data/billing_rules.json", "r") as f:
        rules = cast(dict[str, Any], json.load(f))

    rows: list[dict[str, Any]] = []

    # Duplicate detection
    dup = rules["duplicate_detection"]
    rows.append({
        "rule_type": "duplicate",
        "rule_name": "Duplicate Charge Detection",
        "severity": dup["severity"],
        "description": dup["rule"],
        "trigger_codes": None,
        "condition": json.dumps({"check": "same_cpt_same_date"}),
        "source": "CMS/NCCI",
    })

    # Upcoding rules
    for rule in cast(list[dict[str, Any]], rules["upcoding_rules"]):
        rows.append({
            "rule_type": "upcoding",
            "rule_name": f"Upcoding: {', '.join(rule['diagnosis_names'][:2])}",
            "severity": rule["severity"],
            "description": rule["explanation"],
            "trigger_codes": json.dumps({
                "diagnosis_codes": rule["diagnosis_codes"],
                "diagnosis_names": rule["diagnosis_names"],
            }),
            "condition": json.dumps({
                "check": "em_level_vs_diagnosis",
                "max_expected_em_level": rule["max_expected_em_level"],
            }),
            "source": "CMS/NCCI",
        })

    # Unbundling rules
    for rule in cast(list[dict[str, Any]], rules["unbundling_rules"]):
        rows.append({
            "rule_type": "unbundling",
            "rule_name": f"Unbundling: {' + '.join(rule['code_names'][:2])}",
            "severity": rule["severity"],
            "description": rule["rule"],
            "trigger_codes": json.dumps({
                "cpt_codes": rule["codes"],
                "code_names": rule["code_names"],
            }),
            "condition": json.dumps({
                "check": "codes_billed_together",
                "conflicting_codes": rule["codes"],
            }),
            "source": "CMS/NCCI",
        })

    # Overcharge thresholds
    oc = rules["overcharge_thresholds"]
    rows.append({
        "rule_type": "overcharge",
        "rule_name": "Overcharge Threshold Detection",
        "severity": "HIGH",
        "description": oc["explanation"],
        "trigger_codes": None,
        "condition": json.dumps({
            "check": "charge_vs_medicare_rate",
            "minor_percent": oc["minor_overcharge_percent"],
            "major_percent": oc["major_overcharge_percent"],
            "extreme_percent": oc["extreme_overcharge_percent"],
        }),
        "source": "CMS PFS",
    })

    # Clear existing and insert fresh
    client.table("billing_rules").delete().neq("id", 0).execute()
    client.table("billing_rules").insert(rows).execute()

    print(f"   ✅ Loaded {len(rows)} rules")
    for r in rows:
        print(f"      [{r['severity']}] {r['rule_type']}: {r['rule_name']}")

    return len(rows)


def load_sample_bills(client: Any) -> int:
    """Load sample_bills.json into Supabase."""
    print("\n📥 Loading sample bills...")

    with open("data/sample_bills.json", "r") as f:
        data = cast(dict[str, Any], json.load(f))

    difficulty_map = {
        "demo_clean": "easy",
        "demo_errors": "medium",
        "demo_complex": "hard",
    }

    rows: list[dict[str, Any]] = []
    for bill in cast(list[dict[str, Any]], data["bills"]):
        rows.append({
            "bill_id": bill["id"],
            "name": bill["name"],
            "description": bill.get("description", ""),
            "bill_text": bill["bill_text"],
            "difficulty": difficulty_map.get(bill["id"], "medium"),
            "expected_errors": json.dumps(bill.get("expected_errors", [])),
            "estimated_savings_low": bill.get("estimated_savings_low"),
            "estimated_savings_high": bill.get("estimated_savings_high"),
            "is_demo": True,
        })

    client.table("sample_bills").upsert(rows, on_conflict="bill_id").execute()
    print(f"   ✅ Loaded {len(rows)} bills")
    for r in rows:
        print(f"      [{r['difficulty']}] {r['name']}")

    return len(rows)


# ──────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────

def verify_data(client: Any) -> None:
    """Verify all data loaded correctly."""
    print("\n🔍 Verifying data...")

    # Medicare rates
    result: Any = client.table("medicare_rates").select("cpt_code", count="exact").execute()
    count = cast(int, getattr(result, "count", 0) or 0)
    test: Any = client.table("medicare_rates").select("*").eq("cpt_code", "99213").execute()
    test_rows = cast(list[dict[str, Any]], getattr(test, "data", []) or [])
    if test_rows:
        r = test_rows[0]
        print(f"   ✅ medicare_rates: {count} codes")
        print(f"      Test → 99213 = '{r['description']}' | ${r['non_facility_rate']} | {r['category']}")
    else:
        print(f"   ❌ medicare_rates: CPT 99213 not found (loaded {count} codes)")

    # Billing rules
    result = client.table("billing_rules").select("id", count="exact").eq("is_active", True).execute()
    print(f"   ✅ billing_rules: {cast(int, getattr(result, 'count', 0) or 0)} active rules")

    # Sample bills
    result = client.table("sample_bills").select("id", count="exact").execute()
    print(f"   ✅ sample_bills: {cast(int, getattr(result, 'count', 0) or 0)} bills")

    # Analysis results (should be empty)
    result = client.table("analysis_results").select("id", count="exact").execute()
    print(f"   ✅ analysis_results: {cast(int, getattr(result, 'count', 0) or 0)} entries (should be 0)")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🛡️  BILLSHIELD — Supabase Data Loader")
    print("=" * 60)

    if "--schema" in sys.argv:
        print(SCHEMA_SQL)
        print("\n📋 Copy the SQL above → Supabase Dashboard → SQL Editor → Run")
        sys.exit(0)

    if "--verify" in sys.argv:
        verify_data(get_supabase_client())
        sys.exit(0)

    # Full load
    print("\n⚠️  Make sure you've already run the SQL schema in Supabase!")
    print("   (Run 'python load_supabase.py --schema' to see the SQL)")
    response = input("\n   Have you created the tables? (y/n): ")
    if response.lower() != "y":
        print("\n   Run 'python load_supabase.py --schema' first, then paste into SQL Editor.")
        sys.exit(0)

    client = get_supabase_client()

    rates = load_medicare_rates(client)
    rules = load_billing_rules(client)
    bills = load_sample_bills(client)

    verify_data(client)

    print(f"\n{'='*60}")
    print(f"🟢 ALL DATA LOADED")
    print(f"   {rates} CPT codes | {rules} billing rules | {bills} sample bills")
    print(f"{'='*60}")
