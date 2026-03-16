export interface ParsedCharge {
  cpt_code: string;
  description: string;
  charge: number;
  quantity: number;
  modifier?: string;
}

export interface ICDCode {
  code: string;
  description: string;
  valid: boolean;
}

export interface PricingResult {
  cpt_code: string;
  description: string;
  billed: number;
  medicare_rate: number;
  overcharge_pct: number;
  overcharge_amount: number;
  severity: "FAIR" | "UNDER" | "MINOR" | "MAJOR" | "EXTREME" | "UNKNOWN";
  found: boolean;
  category?: string;
}

export interface BillingError {
  type: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  description: string;
  cpt_codes: string[];
  evidence: string;
  rule_source: string;
  potential_savings_low: number;
  potential_savings_high: number;
  confidence: "LOW" | "MEDIUM" | "HIGH";
}

export interface PatientRight {
  title: string;
  description: string;
  source_url: string;
  applies_to: string[];
  relevance: string;
  status?: string;
  verification_notes?: string;
}

export interface BillMetadata {
  patient_name?: string;
  account_number?: string;
  facility?: string;
  date_of_service?: string;
}

export interface AnalysisResult {
  session_id: string;
  bill_text: string;
  parsed_charges: ParsedCharge[];
  icd_codes: ICDCode[];
  bill_metadata: BillMetadata;
  pricing_results: PricingResult[];
  total_billed: number;
  total_fair: number;
  total_overcharge: number;
  errors_found: BillingError[];
  error_count: number;
  patient_rights: PatientRight[];
  verified_rights: PatientRight[];
  dispute_letter: string;
  current_agent: string;
  status: "pending" | "processing" | "complete" | "error";
}

export interface AgentStep {
  name: string;
  status: "pending" | "running" | "complete" | "error";
  duration?: number;
}

export const DEMO_BILL_TEXT = `Valley Regional Medical Center
Patient: Jane Doe
Account Number: VRMC-2026-0316-1007
Date of Service: 03/10/2026

Charges:
- CPT 99214 Office/Outpatient Visit (Established) x1 .......... $420.00
- CPT 80053 Comprehensive Metabolic Panel x1 ................... $210.00
- CPT 80048 Basic Metabolic Panel x1 ........................... $185.00
- CPT 85025 CBC with Differential x1 ........................... $160.00
- CPT 85027 CBC Automated x1 ................................... $145.00
- CPT 93000 Electrocardiogram x1 ............................... $280.00

Diagnoses:
- J06.9 Acute upper respiratory infection, unspecified
- Z23 Encounter for immunization
`;
