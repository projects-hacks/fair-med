#!/usr/bin/env python3
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""
BillShield — Load REAL CMS RVU26B Data into Supabase (safe + auditable)

This loader ingests CMS RVU26B companion files with:
- Deterministic parsing (header detection + typed coercion)
- No silent row loss (reject logging)
- Idempotent upserts with composite conflict keys
- Backward-compatible materialization into medicare_rates

Usage:
    python load_real_cms_data.py
"""

from __future__ import annotations

import csv
import hashlib
import os
import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from dotenv import load_dotenv  # type: ignore[reportMissingImports]

load_dotenv()

RVU_DIR = "data/rvu26b"
EFFECTIVE_YEAR = 2026
RELEASE_TAG = "apr_2026"

PPRRVU_NON_QPP = os.path.join(RVU_DIR, "PPRRVU2026_Apr_nonQPP.csv")
PPRRVU_QPP = os.path.join(RVU_DIR, "PPRRVU2026_Apr_QPP.csv")
GPCI_CSV = os.path.join(RVU_DIR, "GPCI2026.csv")
LOCCO_CSV = os.path.join(RVU_DIR, "26LOCCO.csv")
ANES_CSV = os.path.join(RVU_DIR, "ANES2026.csv")
OPPSCAP_CSV = os.path.join(RVU_DIR, "OPPSCAP_Apr.csv")

DEFAULT_CF_NON_QPP = 33.4009
DEFAULT_CF_QPP = 33.5675


def get_category(cpt_code: str) -> str:
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


def norm_str(value: Any) -> str:
    return str(value or "").strip()


def norm_modifier(value: Any) -> str:
    mod = norm_str(value).upper()
    if mod in {"NA", "N/A", "NONE", "NULL"}:
        return ""
    return mod


def parse_decimal(value: Any) -> float | None:
    text = norm_str(value)
    if not text:
        return None
    upper = text.upper()
    if upper in {"NA", "N/A", "NULL"}:
        return None
    cleaned = text.replace("$", "").replace(",", "")
    return float(cleaned)


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    transient_markers = [
        "sslv3 alert bad record mac",
        "connection reset",
        "timeout",
        "temporarily unavailable",
        "server closed",
    ]
    return any(marker in text for marker in transient_markers)


def _execute_with_retry(fn: Callable[[], Any], retries: int = 4, base_delay: float = 1.0):
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= retries or not _is_transient_error(exc):
                raise
            time.sleep(base_delay * attempt)
    if last_exc:
        raise last_exc


def file_sha256(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def ensure_exists(path: str):
    if not os.path.exists(path):
        print(f"❌ Missing required file: {path}")
        sys.exit(1)


def get_supabase_client():
    from supabase import create_client  # type: ignore[reportMissingImports]

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_KEY in .env")
        sys.exit(1)
    return create_client(url, key)


def start_load_run(client: Any, dataset_name: str, source_file: str, rows_parsed: int, rows_rejected: int) -> int | None:
    payload = {
        "dataset_name": dataset_name,
        "source_file": source_file,
        "file_sha256": file_sha256(source_file),
        "effective_year": EFFECTIVE_YEAR,
        "release_tag": RELEASE_TAG,
        "status": "started",
        "rows_parsed": rows_parsed,
        "rows_rejected": rows_rejected,
    }
    result = _execute_with_retry(lambda: client.table("cms_load_runs").insert(payload).execute())
    if result and getattr(result, "data", None):
        return result.data[0]["id"]
    return None


def complete_load_run(client: Any, run_id: int | None, rows_loaded: int, rows_rejected: int, status: str, notes: str = ""):
    if not run_id:
        return
    _execute_with_retry(
        lambda: client.table("cms_load_runs")
        .update(
            {
                "rows_loaded": rows_loaded,
                "rows_rejected": rows_rejected,
                "status": status,
                "notes": notes,
                "completed_at": "now()",
            }
        )
        .eq("id", run_id)
        .execute()
    )


def insert_rejects(client: Any, run_id: int | None, dataset_name: str, source_file: str, rejects: list[dict[str, Any]]):
    if not rejects:
        return
    rows = []
    for reject in rejects:
        rows.append(
            {
                "load_run_id": run_id,
                "dataset_name": dataset_name,
                "source_file": source_file,
                "row_number": reject.get("row_number"),
                "reject_reason": reject.get("reject_reason", "unknown"),
                "raw_row": reject.get("raw_row"),
            }
        )
    for idx in range(0, len(rows), 500):
        _execute_with_retry(lambda: client.table("cms_row_rejects").insert(rows[idx : idx + 500]).execute())


def dedupe_by_conflict(
    rows: list[dict[str, Any]], on_conflict: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keys = [key.strip() for key in on_conflict.split(",") if key.strip()]
    if not keys:
        return rows, []

    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        if key in seen:
            duplicates.append({"reject_reason": "duplicate_conflict_key", "raw_row": row})
        seen[key] = row
    return list(seen.values()), duplicates


def batch_upsert(client: Any, table_name: str, rows: list[dict[str, Any]], on_conflict: str, batch_size: int = 500):
    loaded = 0
    for idx in range(0, len(rows), batch_size):
        batch = rows[idx : idx + batch_size]
        _execute_with_retry(lambda: client.table(table_name).upsert(batch, on_conflict=on_conflict).execute())
        loaded += len(batch)
    return loaded


def parse_pprrvu_csv(path: str, program_type: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        header_found = False

        for row_number, row in enumerate(reader, start=1):
            if not row or not any(norm_str(cell) for cell in row):
                continue

            if not header_found:
                if norm_str(row[0]).upper() == "HCPCS" and len(row) >= 31:
                    header_found = True
                continue

            try:
                hcpcs = norm_str(row[0]).upper()
                modifier = norm_modifier(row[1]) if len(row) > 1 else ""
                description = norm_str(row[2])

                if len(hcpcs) != 5:
                    raise ValueError("invalid_hcpcs")
                if not description:
                    description = "Unknown"

                status_code = norm_str(row[3]) if len(row) > 3 else None
                payment_indicator = norm_str(row[4]) if len(row) > 4 else None

                work_rvu = parse_decimal(row[5]) if len(row) > 5 else None
                nonfacility_pe_rvu = parse_decimal(row[6]) if len(row) > 6 else None
                facility_pe_rvu = parse_decimal(row[8]) if len(row) > 8 else None
                malpractice_rvu = parse_decimal(row[10]) if len(row) > 10 else None

                nonfacility_total_rvu = parse_decimal(row[11]) if len(row) > 11 else None
                facility_total_rvu = parse_decimal(row[12]) if len(row) > 12 else None

                conversion_factor = parse_decimal(row[25]) if len(row) > 25 else None
                if conversion_factor is None:
                    conversion_factor = DEFAULT_CF_QPP if program_type == "qpp" else DEFAULT_CF_NON_QPP

                published_nonfacility_rate = parse_decimal(row[29]) if len(row) > 29 else None
                published_facility_rate = parse_decimal(row[30]) if len(row) > 30 else None

                computed_nonfacility_rate = None
                computed_facility_rate = None
                if work_rvu is not None and malpractice_rvu is not None:
                    if nonfacility_pe_rvu is not None:
                        computed_nonfacility_rate = round((work_rvu + nonfacility_pe_rvu + malpractice_rvu) * conversion_factor, 4)
                    if facility_pe_rvu is not None:
                        computed_facility_rate = round((work_rvu + facility_pe_rvu + malpractice_rvu) * conversion_factor, 4)

                if computed_nonfacility_rate is None and nonfacility_total_rvu is not None:
                    computed_nonfacility_rate = round(nonfacility_total_rvu * conversion_factor, 4)
                if computed_facility_rate is None and facility_total_rvu is not None:
                    computed_facility_rate = round(facility_total_rvu * conversion_factor, 4)

                records.append(
                    {
                        "effective_year": EFFECTIVE_YEAR,
                        "release_tag": RELEASE_TAG,
                        "program_type": program_type,
                        "hcpcs": hcpcs,
                        "modifier": modifier,
                        "description": description[:500],
                        "status_code": status_code or None,
                        "payment_indicator": payment_indicator or None,
                        "work_rvu": work_rvu,
                        "nonfacility_pe_rvu": nonfacility_pe_rvu,
                        "facility_pe_rvu": facility_pe_rvu,
                        "malpractice_rvu": malpractice_rvu,
                        "nonfacility_total_rvu": nonfacility_total_rvu,
                        "facility_total_rvu": facility_total_rvu,
                        "conversion_factor": conversion_factor,
                        "computed_nonfacility_rate": computed_nonfacility_rate,
                        "computed_facility_rate": computed_facility_rate,
                        "published_nonfacility_rate": published_nonfacility_rate,
                        "published_facility_rate": published_facility_rate,
                        "source_file": path,
                    }
                )
            except Exception as exc:
                rejects.append(
                    {
                        "row_number": row_number,
                        "reject_reason": str(exc)[:120],
                        "raw_row": row,
                    }
                )

    return records, rejects


def parse_gpci_csv(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        header_found = False

        for row_number, row in enumerate(reader, start=1):
            if not row or not any(norm_str(cell) for cell in row):
                continue

            if not header_found:
                if norm_str(row[0]) == "Medicare Administrative Contractor (MAC)":
                    header_found = True
                continue

            try:
                contractor = norm_str(row[0])
                state_code = norm_str(row[1])
                locality_number = norm_str(row[2]).zfill(2)
                locality_name = norm_str(row[3])

                if not contractor or not locality_number:
                    raise ValueError("missing_locality_key")
                if len(contractor) > 10 or not contractor.isdigit():
                    raise ValueError("invalid_contractor")
                if len(locality_number) > 10 or not locality_number.isdigit():
                    raise ValueError("invalid_locality_number")
                if len(state_code) > 5:
                    raise ValueError("invalid_state_code")

                records.append(
                    {
                        "effective_year": EFFECTIVE_YEAR,
                        "contractor": contractor,
                        "state_code": state_code,
                        "locality_number": locality_number,
                        "locality_name": locality_name,
                        "pw_gpci_without_floor": parse_decimal(row[4]) if len(row) > 4 else None,
                        "pw_gpci_with_floor": parse_decimal(row[5]) if len(row) > 5 else None,
                        "pe_gpci": parse_decimal(row[6]) if len(row) > 6 else None,
                        "mp_gpci": parse_decimal(row[7]) if len(row) > 7 else None,
                        "source_file": path,
                    }
                )
            except Exception as exc:
                rejects.append(
                    {
                        "row_number": row_number,
                        "reject_reason": str(exc)[:120],
                        "raw_row": row,
                    }
                )

    return records, rejects


def parse_locco_csv(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    current_state = ""

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        header_found = False

        for row_number, row in enumerate(reader, start=1):
            if not row or not any(norm_str(cell) for cell in row):
                continue

            if not header_found:
                if norm_str(row[0]) == "Medicare Adminstrative Contractor":
                    header_found = True
                continue

            try:
                contractor = norm_str(row[0])
                locality_number = norm_str(row[1]).zfill(2)
                state_name = norm_str(row[2])
                fee_schedule_area = norm_str(row[3])
                counties_raw = norm_str(row[4]) if len(row) > 4 else ""

                if not contractor or not locality_number or not fee_schedule_area:
                    raise ValueError("missing_crosswalk_key")

                if state_name:
                    current_state = state_name
                state_name = state_name or current_state

                records.append(
                    {
                        "effective_year": EFFECTIVE_YEAR,
                        "contractor": contractor,
                        "locality_number": locality_number,
                        "state_name": state_name,
                        "fee_schedule_area": fee_schedule_area,
                        "counties_raw": counties_raw,
                        "source_file": path,
                    }
                )
            except Exception as exc:
                rejects.append(
                    {
                        "row_number": row_number,
                        "reject_reason": str(exc)[:120],
                        "raw_row": row,
                    }
                )

    return records, rejects


def parse_anes_csv(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                contractor = norm_str(row.get("Contractor"))
                locality_number = norm_str(row.get("Locality")).zfill(2)
                locality_name = norm_str(row.get("Locality Name"))
                if not contractor or not locality_number:
                    raise ValueError("missing_anes_key")

                records.append(
                    {
                        "effective_year": EFFECTIVE_YEAR,
                        "contractor": contractor,
                        "locality_number": locality_number,
                        "locality_name": locality_name,
                        "qpp_anes_cf": parse_decimal(
                            row.get("Qualifying APM National Anes CF (with 2.5% statutory increase) of 20.599835")
                        ),
                        "non_qpp_anes_cf": parse_decimal(
                            row.get("Non-Qualifying APM National Anes CF (with 2.5% Statutory increase)  of 20.49754")
                        ),
                        "source_file": path,
                    }
                )
            except Exception as exc:
                rejects.append(
                    {
                        "row_number": row_number,
                        "reject_reason": str(exc)[:120],
                        "raw_row": row,
                    }
                )

    return records, rejects


def parse_oppscap_csv(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []

    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                hcpcs = norm_str(row.get("HCPCS")).upper()
                modifier = norm_modifier(row.get("MOD"))
                contractor = norm_str(row.get("CARRIER"))
                locality_number = norm_str(row.get("LOCALITY")).zfill(2)

                if len(hcpcs) != 5 or not contractor or not locality_number:
                    raise ValueError("missing_opps_key")

                records.append(
                    {
                        "effective_year": EFFECTIVE_YEAR,
                        "release_tag": RELEASE_TAG,
                        "hcpcs": hcpcs,
                        "modifier": modifier,
                        "procstat": norm_str(row.get("PROCSTAT")) or None,
                        "contractor": contractor,
                        "locality_number": locality_number,
                        "facility_price": parse_decimal(row.get("FACILITY PRICE")),
                        "nonfacility_price": parse_decimal(row.get("NON-FACILTY PRICE")),
                        "source_file": path,
                    }
                )
            except Exception as exc:
                rejects.append(
                    {
                        "row_number": row_number,
                        "reject_reason": str(exc)[:120],
                        "raw_row": row,
                    }
                )

    return records, rejects


def ingest_dataset(
    client: Any,
    dataset_name: str,
    source_file: str,
    parser: Callable[[str], tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    table_name: str,
    on_conflict: str,
) -> tuple[int, int, int]:
    records, rejects = parser(source_file)
    records, duplicate_rejects = dedupe_by_conflict(records, on_conflict)
    rejects.extend(duplicate_rejects)
    run_id = start_load_run(client, dataset_name, source_file, len(records), len(rejects))

    for record in records:
        record["load_run_id"] = run_id
    loaded_count = 0
    status = "completed"
    notes = ""

    try:
        loaded_count = batch_upsert(client, table_name, records, on_conflict=on_conflict, batch_size=100)
        insert_rejects(client, run_id, dataset_name, source_file, rejects)
    except Exception as exc:
        status = "failed"
        notes = str(exc)[:500]
    finally:
        complete_load_run(client, run_id, loaded_count, len(rejects), status=status, notes=notes)

    print(
        f"   ✅ {dataset_name}: parsed={len(records)} loaded={loaded_count} rejected={len(rejects)}"
        if status == "completed"
        else f"   ❌ {dataset_name}: parsed={len(records)} loaded={loaded_count} rejected={len(rejects)} error={notes}"
    )

    return len(records), loaded_count, len(rejects)


def materialize_compat_medicare_rates(client: Any):
    """Keep legacy medicare_rates table usable by current Pricing agent logic."""
    all_rows: list[dict[str, Any]] = []
    page = 0
    page_size = 1000
    while True:
        start = page * page_size
        end = start + page_size - 1
        response = _execute_with_retry(
            lambda s=start, e=end: client.table("cms_pfs_rvu")
            .select(
                "hcpcs, modifier, description, computed_facility_rate, computed_nonfacility_rate, "
                "published_facility_rate, published_nonfacility_rate"
            )
            .eq("effective_year", EFFECTIVE_YEAR)
            .eq("release_tag", RELEASE_TAG)
            .eq("program_type", "non_qpp")
            .range(s, e)
            .execute()
        )
        batch = list(getattr(response, "data", []) or [])
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        page += 1

    best_by_code: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        code = row["hcpcs"]
        score = 1 if not row.get("modifier") else 0
        current = best_by_code.get(code)
        if current is None or score > current["_score"]:
            best_by_code[code] = {"_score": score, **row}

    rows = []
    for code, row in best_by_code.items():
        nonfac = row.get("published_nonfacility_rate") or row.get("computed_nonfacility_rate") or 0
        fac = row.get("published_facility_rate") or row.get("computed_facility_rate") or nonfac
        rows.append(
            {
                "cpt_code": code,
                "description": (row.get("description") or "Unknown")[:500],
                "category": get_category(code),
                "facility_rate": round(float(fac), 2),
                "non_facility_rate": round(float(nonfac), 2),
                "effective_year": EFFECTIVE_YEAR,
                "source": "CMS PFS RVU26B non_qpp national (compat)",
            }
        )

    if rows:
        batch_upsert(client, "medicare_rates", rows, on_conflict="cpt_code")
    print(f"   ✅ materialized legacy medicare_rates rows: {len(rows)}")


def freeze_rebuild_compat_medicare_rates(client: Any):
    """
    One-time controlled rebuild of medicare_rates so only current RVU26B
    compatibility rows remain (no legacy leftovers).
    """
    print("\n🧊 Freeze rebuild: clearing medicare_rates before rematerialization...")
    _execute_with_retry(lambda: client.table("medicare_rates").delete().neq("id", 0).execute())
    materialize_compat_medicare_rates(client)


def _chunked(values: list[int], size: int = 500):
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def cleanup_audit_history(client: Any, keep_last_runs: int = 60, keep_days: int | None = None):
    """
    Periodic cleanup for cms_load_runs and cms_row_rejects.
    - Keeps latest N runs by id (default 60)
    - Optionally keeps only runs newer than keep_days as an additional filter
    """
    print("\n🧹 Cleaning audit history...")
    runs_response = _execute_with_retry(
        lambda: client.table("cms_load_runs")
        .select("id,started_at")
        .order("id", desc=True)
        .execute()
    )
    runs = list(getattr(runs_response, "data", []) or [])

    if not runs:
        print("   ℹ️ No load runs found; nothing to clean")
        return

    cutoff = None
    if keep_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)

    keep_ids: set[int] = set()
    for index, row in enumerate(runs):
        run_id = int(row["id"])
        keep_by_index = index < keep_last_runs

        keep_by_days = False
        if cutoff is not None:
            started_at_text = (row.get("started_at") or "").replace("Z", "+00:00")
            try:
                started_at = datetime.fromisoformat(started_at_text)
                keep_by_days = started_at >= cutoff
            except Exception:
                keep_by_days = False

        if keep_by_index or keep_by_days:
            keep_ids.add(run_id)

    delete_ids = [int(row["id"]) for row in runs if int(row["id"]) not in keep_ids]
    if not delete_ids:
        print("   ℹ️ Nothing to delete based on retention policy")
        return

    rejects_deleted = 0
    runs_deleted = 0

    for batch in _chunked(delete_ids, size=200):
        reject_result = _execute_with_retry(
            lambda b=batch: client.table("cms_row_rejects").delete().in_("load_run_id", b).execute()
        )
        run_result = _execute_with_retry(
            lambda b=batch: client.table("cms_load_runs").delete().in_("id", b).execute()
        )

        rejects_deleted += len(getattr(reject_result, "data", []) or [])
        runs_deleted += len(getattr(run_result, "data", []) or [])

    print(
        f"   ✅ Cleanup complete: deleted_runs={runs_deleted}, deleted_reject_rows={rejects_deleted}, kept_runs={len(keep_ids)}"
    )


def verify_counts(client: Any):
    checks = [
        ("cms_pfs_rvu", "hcpcs"),
        ("cms_gpci_locality", "contractor"),
        ("cms_locality_crosswalk", "contractor"),
        ("cms_anes_cf", "contractor"),
        ("cms_oppscap_pricing", "hcpcs"),
        ("cms_row_rejects", "id"),
        ("medicare_rates", "cpt_code"),
    ]
    print("\n🔍 Verification")
    for table, field in checks:
        res = client.table(table).select(field, count="exact").execute()
        print(f"   {table}: {res.count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load CMS Medicare RVU26B datasets into Supabase")
    parser.add_argument(
        "--freeze-compat",
        action="store_true",
        help="Clear and rebuild medicare_rates to only current RVU26B compatibility rows",
    )
    parser.add_argument(
        "--cleanup-history",
        action="store_true",
        help="Cleanup old cms_load_runs and cms_row_rejects entries",
    )
    parser.add_argument(
        "--keep-last-runs",
        type=int,
        default=60,
        help="Retention target for latest load runs when using --cleanup-history (default: 60)",
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=None,
        help="Optional additional retention by age in days when using --cleanup-history",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("🛡️  BillShield — CMS Medicare RVU26B Loader (auditable + idempotent)")
    print("=" * 72)

    required_files = [PPRRVU_NON_QPP, PPRRVU_QPP, GPCI_CSV, LOCCO_CSV, ANES_CSV, OPPSCAP_CSV]
    for required in required_files:
        ensure_exists(required)

    client = get_supabase_client()

    print("\n📥 Ingesting RVU26B datasets...")

    ingest_dataset(
        client,
        dataset_name="pprrvu_non_qpp",
        source_file=PPRRVU_NON_QPP,
        parser=lambda file_path: parse_pprrvu_csv(file_path, "non_qpp"),
        table_name="cms_pfs_rvu",
        on_conflict="effective_year,release_tag,program_type,hcpcs,modifier",
    )

    ingest_dataset(
        client,
        dataset_name="pprrvu_qpp",
        source_file=PPRRVU_QPP,
        parser=lambda file_path: parse_pprrvu_csv(file_path, "qpp"),
        table_name="cms_pfs_rvu",
        on_conflict="effective_year,release_tag,program_type,hcpcs,modifier",
    )

    ingest_dataset(
        client,
        dataset_name="gpci_2026",
        source_file=GPCI_CSV,
        parser=parse_gpci_csv,
        table_name="cms_gpci_locality",
        on_conflict="effective_year,contractor,state_code,locality_number",
    )

    ingest_dataset(
        client,
        dataset_name="locco_2026",
        source_file=LOCCO_CSV,
        parser=parse_locco_csv,
        table_name="cms_locality_crosswalk",
        on_conflict="effective_year,contractor,locality_number,fee_schedule_area",
    )

    ingest_dataset(
        client,
        dataset_name="anes_2026",
        source_file=ANES_CSV,
        parser=parse_anes_csv,
        table_name="cms_anes_cf",
        on_conflict="effective_year,contractor,locality_number",
    )

    ingest_dataset(
        client,
        dataset_name="oppscap_apr_2026",
        source_file=OPPSCAP_CSV,
        parser=parse_oppscap_csv,
        table_name="cms_oppscap_pricing",
        on_conflict="effective_year,release_tag,hcpcs,modifier,contractor,locality_number",
    )

    if args.freeze_compat:
        freeze_rebuild_compat_medicare_rates(client)
    else:
        print("\n📦 Refreshing compatibility tables...")
        materialize_compat_medicare_rates(client)

    if args.cleanup_history:
        cleanup_audit_history(client, keep_last_runs=max(1, args.keep_last_runs), keep_days=args.keep_days)

    verify_counts(client)

    print("\n✅ RVU26B ingestion completed.")
