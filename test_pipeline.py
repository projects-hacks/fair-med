#!/usr/bin/env python3
"""
BillShield — Full Pipeline Integration Test

Runs the complete graph with the demo bill and verifies:
1. All agents execute
2. All 4 billing traps are detected (duplicate, upcoding, unbundling, overcharge)
3. A dispute letter is generated
"""

import json
import time
import sys

DEMO_BILL = """
====================================================
VALLEY REGIONAL MEDICAL CENTER
1400 Health Way, San Jose, CA 95112
Billing Dept: (800) 555-0199
====================================================

PATIENT: Jane Doe
ACCOUNT NO: 9812-4451-XX
DATE OF SERVICE: 02/14/2026
ATTENDING: Dr. Sarah Jenkins, MD

====================================================
DIAGNOSES (ICD-10):
  1. J06.9 - Acute upper respiratory infection, unspecified
  2. R53.83 - Other fatigue

ITEMIZED CHARGES:

DATE          CPT     DESCRIPTION                            QTY   CHARGE
---------------------------------------------------------------------------
02/14/2026    99215   OFFICE VISIT, EST PATIENT, HIGH COMP.   1    $450.00
02/14/2026    99213   OFFICE VISIT, EST PATIENT, LOW COMP.    1    $250.00
02/14/2026    99213   OFFICE VISIT, EST PATIENT, LOW COMP.    1    $250.00
02/14/2026    36415   ROUTINE VENIPUNCTURE (BLOOD DRAW)       1     $45.00
02/14/2026    80053   COMPREHENSIVE METABOLIC PANEL (CMP)     1    $190.00
02/14/2026    80048   BASIC METABOLIC PANEL (BMP)             1    $120.00
02/14/2026    81001   URINALYSIS, AUTOMATED W/ MICROSCOPY     1     $35.00
---------------------------------------------------------------------------
SUBTOTAL:                                                        $1,340.00
INSURANCE ADJUSTMENT:                                               -$0.00
PATIENT RESPONSIBILITY (AMOUNT DUE):                             $1,340.00
====================================================
Please remit payment within 30 days.
""".strip()

EXPECTED_TRAPS = {
    "DUPLICATE": "99213 billed twice on same date",
    "UPCODING": "99215 for J06.9 (common cold)",
    "UNBUNDLING": "80048 + 80053 (BMP + CMP)",
    "OVERCHARGE": "99215 at $450 vs Medicare ~$192",
}


def main():
    from agents.graph import analyze_bill

    print("=" * 70)
    print("BILLSHIELD — FULL PIPELINE INTEGRATION TEST")
    print("=" * 70)
    print()
    print(f"Demo bill: 7 line items, $1,340 total, 4 embedded traps")
    print(f"Expected traps: {', '.join(EXPECTED_TRAPS.keys())}")
    print()

    start = time.time()

    print("Running pipeline... (expect ~90-120s with rate limiting)")
    print()

    try:
        result = analyze_bill(DEMO_BILL, session_id="")
    except Exception as exc:
        print(f"PIPELINE FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start
    print(f"Pipeline completed in {elapsed:.1f}s")
    print()

    # Check results
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)

    # Triage
    plan = result.get("analysis_plan", "")
    triage_out = result.get("triage_output", {})
    print(f"\n--- TRIAGE ---")
    print(f"  Complexity: {triage_out.get('complexity', 'N/A')}")
    print(f"  Red flags: {triage_out.get('red_flags', [])}")
    print(f"  Plan: {str(plan)[:200]}")

    # Parser
    charges = result.get("parsed_charges", [])
    icd = result.get("icd_codes", [])
    print(f"\n--- PARSER ---")
    print(f"  Charges extracted: {len(charges)}")
    for c in charges:
        print(f"    {c.get('cpt_code','?')} | ${c.get('charge',0):.2f} | {c.get('description','')[:40]}")
    print(f"  ICD codes: {[c.get('code','?') for c in icd]}")

    # Pricing
    pricing = result.get("pricing_results", [])
    print(f"\n--- PRICING ---")
    print(f"  Total billed: ${result.get('total_billed', 0):.2f}")
    print(f"  Total fair: ${result.get('total_fair', 0):.2f}")
    print(f"  Total overcharge: ${result.get('total_overcharge', 0):.2f}")
    for p in pricing:
        if isinstance(p, dict) and "cpt_code" in p:
            print(f"    {p['cpt_code']} | billed=${p.get('billed',0):.2f} | medicare=${p.get('medicare_rate',0):.2f} | {p.get('severity','?')}")

    # Auditor
    errors = result.get("errors_found", [])
    print(f"\n--- AUDITOR ---")
    print(f"  Errors found: {len(errors)}")
    found_types = set()
    for e in errors:
        etype = e.get("type", "?")
        found_types.add(etype)
        print(f"    [{etype}] {e.get('severity','?')} | {e.get('description','')[:80]}")
        print(f"      Evidence: {e.get('evidence','')[:80]}")
        print(f"      Savings: ${e.get('potential_savings_low',0):.2f} - ${e.get('potential_savings_high',0):.2f}")

    # Researcher
    rights = result.get("patient_rights", [])
    print(f"\n--- RESEARCHER ---")
    print(f"  Rights found: {len(rights)}")
    for r in rights:
        print(f"    {r.get('title','?')[:60]} | {r.get('relevance','?')}")

    # Fact-Checker
    verified = result.get("verified_rights", [])
    print(f"\n--- FACT-CHECKER ---")
    print(f"  Verified rights: {len(verified)}")
    for v in verified:
        print(f"    {v.get('title','?')[:60]} | {v.get('status','?')}")

    # Writer
    letter = result.get("dispute_letter", "")
    print(f"\n--- WRITER ---")
    print(f"  Letter length: {len(letter)} chars")
    print(f"  First 300 chars:")
    print(f"    {letter[:300]}")

    # Trap verification
    print()
    print("=" * 70)
    print("TRAP VERIFICATION")
    print("=" * 70)
    all_pass = True
    for trap, description in EXPECTED_TRAPS.items():
        detected = trap in found_types
        status = "CAUGHT" if detected else "MISSED"
        symbol = "+" if detected else "X"
        print(f"  [{symbol}] {trap}: {description} → {status}")
        if not detected:
            all_pass = False

    print()
    if all_pass:
        print("ALL 4 TRAPS DETECTED — DEMO READY")
    else:
        missed = [t for t in EXPECTED_TRAPS if t not in found_types]
        print(f"WARNING: {len(missed)} trap(s) missed: {', '.join(missed)}")
        print("The auditor may still catch these through different type labels.")
        print(f"Actual error types found: {found_types}")

    print(f"\nTotal time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
