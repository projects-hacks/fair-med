#!/usr/bin/env python3
"""
Fetch latest CMS NCCI source files (PTP + MUE) for hackathon use.

This script downloads the latest quarter's publicly available ZIP files from:
- Medicare NCCI Procedure to Procedure (PTP) Edits page
- Medicare NCCI Medically Unlikely Edits (MUE) page

Outputs:
- data/ncci/raw/*.zip
- data/ncci/raw/manifest.json

Usage:
  python fetch_ncci_latest.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import requests

PTP_PAGE = "https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits"
MUE_PAGE = "https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits-mues"

RAW_DIR = "data/ncci/raw"
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")


@dataclass
class Asset:
    kind: str
    quarter: str
    url: str

    @property
    def filename(self) -> str:
        name = self.url.split("/")[-1]
        return name.split("?")[0]

    @property
    def output_path(self) -> str:
        return os.path.join(RAW_DIR, self.filename)


# Fallback URLs verified from CMS pages as of 2026-03-16.
FALLBACK_ASSETS = [
    Asset(
        "ptp_hospital_changes",
        "2026Q2",
        "https://www.cms.gov/files/zip/medicare-ncci-2026q2-hospital-quarterly-additions-deletions-revisions-ptp.zip",
    ),
    Asset(
        "ptp_practitioner_changes",
        "2026Q2",
        "https://www.cms.gov/files/zip/medicare-ncci-2026q2-practitioner-quarterly-additions-deletions-revisions-ptp.zip",
    ),
    Asset(
        "mue_dme_table",
        "2026Q2",
        "https://www.cms.gov/files/zip/medicare-ncci-2026-q2-dme-supplier-services-mue-table.zip",
    ),
    Asset(
        "mue_facility_table",
        "2026Q2",
        "https://www.cms.gov/files/zip/medicare-ncci-2026-q2-facility-outpatient-hospital-services-mue-table.zip",
    ),
    Asset(
        "mue_practitioner_table",
        "2026Q2",
        "https://www.cms.gov/files/zip/medicare-ncci-2026-q2-practitioner-services-mue-table.zip",
    ),
]


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.text


def normalize_url(raw_url: str) -> str:
    url = raw_url.replace("&amp;", "&")
    if url.startswith("/"):
        return f"https://www.cms.gov{url}"
    if url.startswith("https://www.cms.gov/license/ama?file="):
        # Convert AMA gateway link to direct file link.
        file_path = url.split("file=", 1)[1]
        if not file_path.startswith("/"):
            file_path = f"/{file_path}"
        return f"https://www.cms.gov{file_path}"
    return url


def extract_zip_links(html: str) -> list[str]:
    pattern = re.compile(r'https?://[^"\']+?\.zip(?:\?[^"\']*)?', re.IGNORECASE)
    matches = pattern.findall(html)
    return sorted({normalize_url(url) for url in matches})


def quarter_from_url(url: str) -> str | None:
    match = re.search(r"(20\d{2})[-_]?q([1-4])", url.lower())
    if match:
        return f"{match.group(1)}Q{match.group(2)}"

    # Some MUE announcement files encode only effective date in MMDDYYYY.
    date_match = re.search(r"(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(20\d{2})", url)
    if date_match:
        month = int(date_match.group(1))
        year = int(date_match.group(3))
        quarter = (month - 1) // 3 + 1
        return f"{year}Q{quarter}"

    return None


def quarter_rank(q: str) -> tuple[int, int]:
    year, quarter = q.split("Q")
    return int(year), int(quarter)


def latest_quarter(quarters: Iterable[str]) -> str | None:
    quarters = [q for q in quarters if q]
    if not quarters:
        return None
    return sorted(set(quarters), key=quarter_rank)[-1]


def pick_latest_assets(ptp_links: list[str], mue_links: list[str]) -> list[Asset]:
    quarter_by_ptp = {url: quarter_from_url(url) for url in ptp_links}
    quarter_by_mue = {url: quarter_from_url(url) for url in mue_links}

    latest_ptp_q = latest_quarter([q for q in quarter_by_ptp.values() if q])
    latest_mue_q = latest_quarter([q for q in quarter_by_mue.values() if q])

    assets: list[Asset] = []

    # Prefer quarterly additions/deletions for PTP (public, no AMA gate).
    if latest_ptp_q:
        for url, quarter in quarter_by_ptp.items():
            if quarter != latest_ptp_q:
                continue
            if not quarter:
                continue
            low = url.lower()
            if "quarterly-additions-deletions-revisions" in low and "ptp" in low:
                if "practitioner" in low:
                    assets.append(Asset("ptp_practitioner_changes", quarter, url))
                elif "hospital" in low:
                    assets.append(Asset("ptp_hospital_changes", quarter, url))

    # MUE latest quarter tables.
    if latest_mue_q:
        for url, quarter in quarter_by_mue.items():
            if quarter != latest_mue_q:
                continue
            if not quarter:
                continue
            low = url.lower()
            if "mue-table" in low:
                if "practitioner" in low:
                    assets.append(Asset("mue_practitioner_table", quarter, url))
                elif "facility-outpatient-hospital" in low:
                    assets.append(Asset("mue_facility_table", quarter, url))
                elif "dme-supplier" in low:
                    assets.append(Asset("mue_dme_table", quarter, url))

    # Fallback to announcement zips if mue-table links are not detected.
    if not any(asset.kind.startswith("mue_") for asset in assets):
        if latest_mue_q:
            for url, quarter in quarter_by_mue.items():
                if quarter != latest_mue_q:
                    continue
                if not quarter:
                    continue
                low = url.lower()
                if "quarterly-additions-deletions-revisions" in low:
                    if "practitioner" in low:
                        assets.append(Asset("mue_practitioner_changes", quarter, url))
                    elif "outpatient-hospital" in low:
                        assets.append(Asset("mue_hospital_changes", quarter, url))
                    elif "durable-medical" in low:
                        assets.append(Asset("mue_dme_changes", quarter, url))

    # Deduplicate by URL.
    uniq: dict[str, Asset] = {}
    for asset in assets:
        uniq[asset.url] = asset
    return list(uniq.values())


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_asset(asset: Asset) -> dict[str, str | int]:
    response = requests.get(asset.url, timeout=120)
    response.raise_for_status()

    os.makedirs(RAW_DIR, exist_ok=True)
    with open(asset.output_path, "wb") as handle:
        handle.write(response.content)

    return {
        "kind": asset.kind,
        "quarter": asset.quarter,
        "url": asset.url,
        "filename": asset.filename,
        "size_bytes": os.path.getsize(asset.output_path),
        "sha256": sha256_file(asset.output_path),
    }


def main():
    print("📡 Fetching CMS NCCI pages...")
    ptp_html = fetch_html(PTP_PAGE)
    mue_html = fetch_html(MUE_PAGE)

    ptp_links = extract_zip_links(ptp_html)
    mue_links = extract_zip_links(mue_html)

    assets = pick_latest_assets(ptp_links, mue_links)
    if not assets:
        print("⚠️ Dynamic discovery returned no assets; using fallback CMS URLs")
        assets = FALLBACK_ASSETS

    print(f"🔎 Found {len(assets)} latest-quarter assets")
    records: list[dict[str, str | int]] = []
    for asset in assets:
        print(f"  ⬇️  {asset.kind}: {asset.filename}")
        records.append(download_asset(asset))

    manifest: dict[str, Any] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "ptp_page": PTP_PAGE,
            "mue_page": MUE_PAGE,
        },
        "assets": records,
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    print(f"✅ Saved manifest: {MANIFEST_PATH}")
    print("✅ Latest NCCI raw files downloaded")


if __name__ == "__main__":
    main()
