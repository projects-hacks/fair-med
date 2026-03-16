"""
FairMed agent implementations.

Usage for the UI:

    from agents.graph import analyze_bill, generate_letter

    # Phase 1 — run analysis (~210s), returns all findings
    state = analyze_bill(bill_text)

    # Show results to user immediately...
    # If errors found, show "Generate Dispute Letter" button

    # Phase 2 — generate letter on demand (~77s)
    letter = generate_letter(state)
"""
