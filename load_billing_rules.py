#!/usr/bin/env python3
"""
BillShield — Billing Rules Pipeline (NCCI source-driven)

Default flow (source-first):
1) Parse latest raw NCCI files from data/ncci/raw (PTP + MUE)
2) Build in-memory normalized rules
3) Load into Supabase billing_rules table
4) Verify source vs DB counts

Optional:
- Export the generated rules snapshot JSON with --export-json
- Use an existing JSON snapshot with --rules-json

Usage:
    python load_billing_rules.py --load-only
    python load_billing_rules.py --verify-only
    python load_billing_rules.py --build-only
    python load_billing_rules.py --export-json
    python load_billing_rules.py --rules-json data/billing_rules.json --verify-only
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import date
from typing import Any, cast

from dotenv import load_dotenv  # type: ignore[reportMissingImports]

load_dotenv()

RULES_PATH = "data/billing_rules.json"
RAW_NCCI_DIR = "data/ncci/raw"
MANIFEST_PATH = os.path.join(RAW_NCCI_DIR, "manifest.json")


def get_supabase_client():
    try:
        from supabase import create_client  # type: ignore[reportMissingImports]
    except ImportError:
        print("❌ supabase not installed. Run: pip install supabase")
        sys.exit(1)

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env")
        sys.exit(1)

    return create_client(url, key)


def ensure_rules_dir(path: str = RULES_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def parse_ptp_text_from_zip(zip_path: str, scope: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    pattern = re.compile(r"^([A-Z0-9]{4,7})\s+([A-Z0-9]{4,7})\s+([019])$")

    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".txt"):
                continue

            lower_name = name.lower()
            if "addition" in lower_name:
                change_type = "addition"
            elif "deletion" in lower_name:
                change_type = "deletion"
            elif "ccmichg" in lower_name or "ccmi" in lower_name:
                change_type = "ccmi_change"
            else:
                change_type = "change"

            lines = archive.read(name).decode("utf-8", "replace").splitlines()
            start_idx = 0
            for idx, line in enumerate(lines):
                if "Column 1" in line and "Column 2" in line:
                    start_idx = idx + 1
                    break

            for line in lines[start_idx:]:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("Indicator"):
                    continue
                if stripped.startswith("0=") or stripped.startswith("1=") or stripped.startswith("9="):
                    continue
                if stripped.startswith("This file"):
                    continue

                match = pattern.match(stripped)
                if not match:
                    continue

                col1, col2, indicator = match.groups()
                rules.append(
                    {
                        "scope": scope,
                        "change_type": change_type,
                        "column_1": col1,
                        "column_2": col2,
                        "modifier_indicator": indicator,
                    }
                )

    return rules


def parse_mue_csv_from_zip(zip_path: str, scope: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []

    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            return rules

        data = archive.read(csv_names[0]).decode("utf-8", "replace")
        reader = csv.reader(io.StringIO(data))

        header_found = False
        for row in reader:
            if not row:
                continue
            if not header_found:
                joined = " ".join(cell for cell in row if cell)
                if "MUE Adjudication Indicator" in joined and "HCPCS" in joined:
                    header_found = True
                continue

            if len(row) < 4:
                continue

            code = str(row[0] or "").replace("\n", " ").strip()
            mue_value = str(row[1] or "").strip()
            adjudication = str(row[2] or "").strip()
            rationale = str(row[3] or "").strip()

            if not code:
                continue
            if not re.match(r"^[A-Z0-9]{4,7}$", code):
                continue
            if not re.match(r"^\d+$", mue_value):
                continue

            rules.append(
                {
                    "scope": scope,
                    "code": code,
                    "mue_value": int(mue_value),
                    "adjudication_indicator": adjudication,
                    "rationale": rationale,
                }
            )

    return rules


def build_ruleset_from_ncci(raw_dir: str = RAW_NCCI_DIR) -> dict[str, Any]:
    if not os.path.isdir(raw_dir):
        raise FileNotFoundError(f"NCCI raw directory missing: {raw_dir}")

    files = [os.path.join(raw_dir, name) for name in os.listdir(raw_dir) if name.lower().endswith(".zip")]
    if not files:
        raise FileNotFoundError(f"No ZIP files found in {raw_dir}. Run fetch_ncci_latest.py first.")

    ptp_practitioner_zip = next((f for f in files if "practitioner" in os.path.basename(f).lower() and "ptp" in os.path.basename(f).lower()), None)
    ptp_hospital_zip = next((f for f in files if "hospital" in os.path.basename(f).lower() and "ptp" in os.path.basename(f).lower()), None)
    mue_practitioner_zip = next((f for f in files if "practitioner-services-mue-table" in os.path.basename(f).lower()), None)
    mue_hospital_zip = next((f for f in files if "facility-outpatient-hospital-services-mue-table" in os.path.basename(f).lower()), None)
    mue_dme_zip = next((f for f in files if "dme-supplier-services-mue-table" in os.path.basename(f).lower()), None)

    missing = [
        ("ptp_practitioner_zip", ptp_practitioner_zip),
        ("ptp_hospital_zip", ptp_hospital_zip),
        ("mue_practitioner_zip", mue_practitioner_zip),
        ("mue_hospital_zip", mue_hospital_zip),
        ("mue_dme_zip", mue_dme_zip),
    ]
    missing_names = [name for name, value in missing if not value]
    if missing_names:
        raise RuntimeError(f"Missing required NCCI files in {raw_dir}: {missing_names}")

    assert ptp_practitioner_zip is not None
    assert ptp_hospital_zip is not None
    assert mue_practitioner_zip is not None
    assert mue_hospital_zip is not None
    assert mue_dme_zip is not None

    ptp_rules: list[dict[str, Any]] = []
    ptp_rules.extend(parse_ptp_text_from_zip(ptp_practitioner_zip, "practitioner"))
    ptp_rules.extend(parse_ptp_text_from_zip(ptp_hospital_zip, "hospital"))

    mue_rules: list[dict[str, Any]] = []
    mue_rules.extend(parse_mue_csv_from_zip(mue_practitioner_zip, "practitioner"))
    mue_rules.extend(parse_mue_csv_from_zip(mue_hospital_zip, "hospital"))
    mue_rules.extend(parse_mue_csv_from_zip(mue_dme_zip, "dme"))

    version = "latest"
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
                manifest = cast(dict[str, Any], json.load(handle))
            quarters = sorted({asset.get("quarter") for asset in manifest.get("assets", []) if asset.get("quarter")})
            if quarters:
                version = quarters[-1]
        except Exception:
            pass

    rules: dict[str, Any] = {
        "metadata": {
            "primary_source": "CMS NCCI quarterly releases",
            "secondary_source": "CMS E/M documentation guidance",
            "version": version,
            "updated_at": str(date.today()),
            "raw_dir": raw_dir,
            "ptp_rule_count": len(ptp_rules),
            "mue_rule_count": len(mue_rules),
            "notes": "Auto-generated from fetched NCCI ZIPs. Keep E/M heuristics as secondary policy layer.",
        },
        "duplicate_detection": {
            "severity": "HIGH",
            "rule": "Same CPT code billed on the same date of service for the same encounter is likely a duplicate unless valid distinct-service modifier and documentation exist.",
        },
        "upcoding_rules": [
            {
                "diagnosis_codes": ["J06.9", "J00", "J02.9", "J01.90", "J20.9"],
                "diagnosis_names": ["URI", "Common cold", "Pharyngitis", "Sinusitis", "Bronchitis"],
                "max_expected_em_level": "99213",
                "severity": "HIGH",
                "explanation": "Common uncomplicated respiratory infections are usually low-complexity E/M visits unless higher complexity is clinically documented.",
            },
            {
                "diagnosis_codes": ["Z23"],
                "diagnosis_names": ["Immunization encounter"],
                "max_expected_em_level": "99212",
                "severity": "HIGH",
                "explanation": "Immunization-only encounters are typically straightforward; higher E/M levels require separately identifiable evaluation with supporting documentation.",
            },
        ],
        "unbundling_rules": [
            {
                "codes": ["80048", "80053"],
                "code_names": ["Basic metabolic panel", "Comprehensive metabolic panel"],
                "severity": "HIGH",
                "rule": "CMP includes BMP components; billing both together is an NCCI unbundling risk.",
            },
            {
                "codes": ["85025", "85027"],
                "code_names": ["CBC with differential", "CBC without differential"],
                "severity": "HIGH",
                "rule": "CBC with differential includes core CBC components; billing both may violate NCCI PTP edits.",
            },
        ],
        "ncci_ptp_rules": ptp_rules,
        "mue_rules": mue_rules,
        "overcharge_thresholds": {
            "minor_overcharge_percent": 50,
            "major_overcharge_percent": 150,
            "extreme_overcharge_percent": 300,
            "explanation": "Compares billed amounts against Medicare fair rates; larger differentials have progressively higher audit severity.",
        },
    }

    return rules


def write_rules(path: str, rules: dict[str, Any]):
    ensure_rules_dir(path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rules, handle, indent=2)
    print(f"✅ Exported rules snapshot: {path}")


def read_rules(path: str = RULES_PATH) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = cast(dict[str, Any], json.load(handle))

    required = ["duplicate_detection", "upcoding_rules", "unbundling_rules", "overcharge_thresholds"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Missing required keys in {path}: {missing}")
    return data


def build_rows(rules: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = rules.get("metadata", {})
    version = metadata.get("version", "unversioned")

    rows: list[dict[str, Any]] = []

    dup = rules["duplicate_detection"]
    rows.append(
        {
            "rule_type": "duplicate",
            "rule_name": "Duplicate Charge Detection",
            "severity": dup["severity"],
            "description": dup["rule"],
            "trigger_codes": None,
            "condition": json.dumps({"check": "same_cpt_same_date"}),
            "source": f"CMS/NCCI ({version})",
        }
    )

    for rule in rules["upcoding_rules"]:
        rows.append(
            {
                "rule_type": "upcoding",
                "rule_name": f"Upcoding: {', '.join(rule.get('diagnosis_names', [])[:2])}",
                "severity": rule.get("severity", "MEDIUM"),
                "description": rule.get("explanation", ""),
                "trigger_codes": json.dumps(
                    {
                        "diagnosis_codes": rule.get("diagnosis_codes", []),
                        "diagnosis_names": rule.get("diagnosis_names", []),
                    }
                ),
                "condition": json.dumps(
                    {
                        "check": "em_level_vs_diagnosis",
                        "max_expected_em_level": rule.get("max_expected_em_level"),
                    }
                ),
                "source": f"CMS E/M Guidance ({version})",
            }
        )

    for rule in rules["unbundling_rules"]:
        rows.append(
            {
                "rule_type": "unbundling",
                "rule_name": f"Unbundling: {' + '.join(rule.get('code_names', [])[:2])}",
                "severity": rule.get("severity", "HIGH"),
                "description": rule.get("rule", ""),
                "trigger_codes": json.dumps({"cpt_codes": rule.get("codes", []), "code_names": rule.get("code_names", [])}),
                "condition": json.dumps({"check": "codes_billed_together", "conflicting_codes": rule.get("codes", [])}),
                "source": f"CMS NCCI PTP ({version})",
            }
        )

    for rule in rules.get("ncci_ptp_rules", []):
        indicator = rule.get("modifier_indicator", "9")
        severity = "HIGH" if indicator == "0" else "MEDIUM"
        rows.append(
            {
                "rule_type": "unbundling",
                "rule_name": f"NCCI PTP {rule.get('scope', 'unknown')}: {rule.get('column_1')} + {rule.get('column_2')}",
                "severity": severity,
                "description": f"NCCI PTP {rule.get('change_type')} pair with modifier indicator {indicator}.",
                "trigger_codes": json.dumps(
                    {
                        "cpt_codes": [rule.get("column_1"), rule.get("column_2")],
                        "scope": rule.get("scope"),
                        "change_type": rule.get("change_type"),
                    }
                ),
                "condition": json.dumps(
                    {
                        "check": "codes_billed_together",
                        "conflicting_codes": [rule.get("column_1"), rule.get("column_2")],
                        "modifier_indicator": indicator,
                    }
                ),
                "source": f"CMS NCCI PTP Quarterly ({version})",
            }
        )

    for rule in rules.get("mue_rules", []):
        ai = str(rule.get("adjudication_indicator", ""))
        severity = "HIGH" if ai.startswith("2") else "MEDIUM"
        rows.append(
            {
                "rule_type": "mue",
                "rule_name": f"MUE Limit {rule.get('scope', 'unknown')}: {rule.get('code')} <= {rule.get('mue_value')}",
                "severity": severity,
                "description": f"MUE units limit for {rule.get('scope')} with adjudication indicator '{ai}'.",
                "trigger_codes": json.dumps({"cpt_codes": [rule.get("code")], "scope": rule.get("scope")}),
                "condition": json.dumps(
                    {
                        "check": "units_exceed_mue",
                        "code": rule.get("code"),
                        "max_units": rule.get("mue_value"),
                        "adjudication_indicator": ai,
                        "rationale": rule.get("rationale"),
                    }
                ),
                "source": f"CMS NCCI MUE Quarterly ({version})",
            }
        )

    oc = rules["overcharge_thresholds"]
    rows.append(
        {
            "rule_type": "overcharge",
            "rule_name": "Overcharge Threshold Detection",
            "severity": "HIGH",
            "description": oc["explanation"],
            "trigger_codes": None,
            "condition": json.dumps(
                {
                    "check": "charge_vs_medicare_rate",
                    "minor_percent": oc["minor_overcharge_percent"],
                    "major_percent": oc["major_overcharge_percent"],
                    "extreme_percent": oc["extreme_overcharge_percent"],
                }
            ),
            "source": f"CMS PFS ({version})",
        }
    )

    return rows


def load_rules_to_supabase(client: Any, rows: list[dict[str, Any]]):
    client.table("billing_rules").delete().neq("id", 0).execute()

    batch_size = 1000
    loaded = 0
    for idx in range(0, len(rows), batch_size):
        batch = rows[idx : idx + batch_size]
        client.table("billing_rules").insert(batch).execute()
        loaded += len(batch)

    print(f"✅ Loaded {loaded} rows into billing_rules")


def verify_rules(client: Any, rules: dict[str, Any] | None = None):
    result = client.table("billing_rules").select("id,rule_type,severity", count="exact").execute()
    print(f"✅ billing_rules count: {result.count}")

    if rules is not None:
        built_rows = build_rows(rules)
        expected = len(built_rows)
        expected_by_type = Counter(row["rule_type"] for row in built_rows)
        print(f"   expected_rows_from_source: {expected}")
        if result.count != expected:
            print("❌ Mismatch detected between expected and DB count")
            return False

        db_by_type: dict[str, int | None] = {}
        for rule_type, expected_count in sorted(expected_by_type.items()):
            db_count = client.table("billing_rules").select("id", count="exact").eq("rule_type", rule_type).execute().count
            db_by_type[rule_type] = db_count
            if db_count != expected_count:
                print(f"❌ Count mismatch for type '{rule_type}': expected={expected_count}, db={db_count}")
                return False

        print("   by_type:", db_by_type)
        print("✅ Source-to-DB count match")
    else:
        print("   by_type: skipped (rules JSON not provided)")

    sample: list[dict[str, Any]] = (
        client.table("billing_rules").select("rule_type,rule_name,source").order("id").limit(5).execute().data
        or []
    )
    for row in sample:
        print(f"   - [{row['rule_type']}] {row['rule_name']} | {row['source']}")

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-ncci", action="store_true", help="Deprecated: source-first behavior is already default")
    parser.add_argument("--raw-dir", default=RAW_NCCI_DIR, help="Directory containing fetched NCCI raw ZIP files")
    parser.add_argument("--rules-json", default=None, help="Optional input rules JSON path (bypass source parse)")
    parser.add_argument("--export-json", action="store_true", help="Export generated source rules to data/billing_rules.json")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--load-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if args.rules_json:
        rules = read_rules(args.rules_json)
        print(f"✅ Loaded rules from JSON snapshot: {args.rules_json}")
    else:
        rules = build_ruleset_from_ncci(args.raw_dir)
        metadata = cast(dict[str, Any], rules.get("metadata", {}))
        print(
            "✅ Built rules from NCCI source files "
            f"(version={metadata.get('version', 'unknown')}, "
            f"ptp={metadata.get('ptp_rule_count', 0)}, mue={metadata.get('mue_rule_count', 0)})"
        )

    if args.export_json:
        write_rules(RULES_PATH, rules)

    if args.build_only:
        print("✅ Rules build complete.")
        return

    client = get_supabase_client()

    if args.verify_only:
        ok = verify_rules(client, rules)
        if not ok:
            sys.exit(1)
        return

    rows = build_rows(rules)

    if args.load_only or (not args.build_only and not args.verify_only):
        load_rules_to_supabase(client, rows)
        ok = verify_rules(client, rules)
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
