import { NextRequest } from "next/server";

// Simulated agent processing - In production, this would call the Python backend
const AGENT_STEPS = [
  { name: "Triage", duration: 1.2 },
  { name: "Parser", duration: 1.5 },
  { name: "Pricing", duration: 2.0 },
  { name: "Auditor", duration: 2.5 },
  { name: "Researcher", duration: 1.8 },
  { name: "Fact-Checker", duration: 1.3 },
  { name: "Writer", duration: 2.2 },
];

// Parse CPT codes and charges from bill text
function parseBillText(billText: string) {
  const charges: Array<{
    cpt_code: string;
    description: string;
    charge: number;
    quantity: number;
  }> = [];

  const icdCodes: Array<{ code: string; description: string; valid: boolean }> =
    [];

  // Parse CPT codes (format: CPT XXXXX Description ... $XXX.XX)
  const cptRegex = /CPT\s+(\d{5})\s+([^$\n]+?)\s*(?:x(\d+))?\s*\.+\s*\$?([\d,]+\.?\d*)/gi;
  let match;

  while ((match = cptRegex.exec(billText)) !== null) {
    charges.push({
      cpt_code: match[1],
      description: match[2].trim(),
      charge: parseFloat(match[4].replace(",", "")),
      quantity: parseInt(match[3] || "1"),
    });
  }

  // Parse ICD-10 codes (format: X##.# Description)
  const icdRegex = /([A-Z]\d{2}(?:\.\d{1,2})?)\s+([^\n]+)/gi;
  while ((match = icdRegex.exec(billText)) !== null) {
    const code = match[1];
    // Only add if it looks like an ICD code (not CPT)
    if (code.match(/^[A-TV-Z]/i)) {
      icdCodes.push({
        code: code.toUpperCase(),
        description: match[2].trim(),
        valid: true,
      });
    }
  }

  return { charges, icdCodes };
}

// Calculate pricing results
function calculatePricing(
  charges: Array<{
    cpt_code: string;
    description: string;
    charge: number;
    quantity: number;
  }>
) {
  // Simulated Medicare rates for common CPT codes
  const medicareRates: Record<string, number> = {
    "99214": 135.0,
    "99213": 98.0,
    "99215": 188.0,
    "80053": 14.0,
    "80048": 11.0,
    "85025": 10.0,
    "85027": 8.0,
    "93000": 18.0,
    "36415": 3.0,
    "81001": 4.0,
  };

  return charges.map((charge) => {
    const medicareRate = medicareRates[charge.cpt_code] || 0;
    const fairTotal = medicareRate * charge.quantity;
    const overchargeAmount = Math.max(charge.charge - fairTotal, 0);
    const overchargePct =
      fairTotal > 0 ? ((charge.charge - fairTotal) / fairTotal) * 100 : 0;

    let severity: string;
    if (overchargePct >= 300) severity = "EXTREME";
    else if (overchargePct >= 100) severity = "MAJOR";
    else if (overchargePct >= 25) severity = "MINOR";
    else if (overchargePct < 0) severity = "UNDER";
    else severity = "FAIR";

    return {
      cpt_code: charge.cpt_code,
      description: charge.description,
      billed: charge.charge,
      medicare_rate: fairTotal,
      overcharge_pct: Math.round(overchargePct * 10) / 10,
      overcharge_amount: Math.round(overchargeAmount * 100) / 100,
      severity,
      found: medicareRate > 0,
      category: getCategoryForCode(charge.cpt_code),
    };
  });
}

function getCategoryForCode(cptCode: string): string {
  const code = parseInt(cptCode);
  if (code >= 99201 && code <= 99499) return "E&M";
  if (code >= 80000 && code <= 89999) return "Lab";
  if (code >= 70000 && code <= 79999) return "Imaging";
  if (code >= 10000 && code <= 69999) return "Surgery";
  if (code >= 90000 && code <= 96999) return "Vaccine";
  return "Other";
}

// Detect billing errors
function detectErrors(
  charges: Array<{
    cpt_code: string;
    description: string;
    charge: number;
    quantity: number;
  }>,
  pricingResults: Array<{ overcharge_pct: number; cpt_code: string }>
) {
  const errors: Array<{
    type: string;
    severity: string;
    description: string;
    cpt_codes: string[];
    evidence: string;
    rule_source: string;
    potential_savings_low: number;
    potential_savings_high: number;
    confidence: string;
  }> = [];

  const cptCodes = charges.map((c) => c.cpt_code);

  // Check for unbundling (80053 + 80048 is a common example)
  if (cptCodes.includes("80053") && cptCodes.includes("80048")) {
    const c1 = charges.find((c) => c.cpt_code === "80048");
    errors.push({
      type: "UNBUNDLING",
      severity: "HIGH",
      description:
        "CPT 80048 (Basic Metabolic Panel) is a subset of CPT 80053 (Comprehensive Metabolic Panel). Billing both is considered unbundling.",
      cpt_codes: ["80053", "80048"],
      evidence:
        "NCCI PTP Edits indicate these codes should not be billed together.",
      rule_source: "NCCI PTP Practitioner Edits 2026Q2",
      potential_savings_low: c1?.charge || 0,
      potential_savings_high: c1?.charge || 0,
      confidence: "HIGH",
    });
  }

  // Check for duplicate CBC codes
  if (cptCodes.includes("85025") && cptCodes.includes("85027")) {
    const c1 = charges.find((c) => c.cpt_code === "85027");
    errors.push({
      type: "DUPLICATE",
      severity: "HIGH",
      description:
        "CPT 85025 (CBC with Differential) includes CPT 85027 (CBC Automated). Billing both is duplicate billing.",
      cpt_codes: ["85025", "85027"],
      evidence:
        "85025 is a more comprehensive test that includes the components of 85027.",
      rule_source: "NCCI PTP Practitioner Edits 2026Q2",
      potential_savings_low: c1?.charge || 0,
      potential_savings_high: c1?.charge || 0,
      confidence: "HIGH",
    });
  }

  // Check for major overcharges
  pricingResults.forEach((pr) => {
    if (pr.overcharge_pct >= 200) {
      const charge = charges.find((c) => c.cpt_code === pr.cpt_code);
      if (charge) {
        errors.push({
          type: "OVERCHARGE",
          severity: "MEDIUM",
          description: `CPT ${pr.cpt_code} is billed at ${pr.overcharge_pct.toFixed(0)}% above Medicare fair rate. This may be negotiable.`,
          cpt_codes: [pr.cpt_code],
          evidence: `Billed: $${charge.charge.toFixed(2)}, Medicare rate: $${((charge.charge * 100) / (100 + pr.overcharge_pct)).toFixed(2)}`,
          rule_source: "CMS Medicare Physician Fee Schedule RVU26B",
          potential_savings_low: charge.charge * 0.3,
          potential_savings_high: charge.charge * 0.6,
          confidence: "MEDIUM",
        });
      }
    }
  });

  return errors;
}

// Generate dispute letter
function generateDisputeLetter(
  billText: string,
  errors: Array<{
    type: string;
    description: string;
    cpt_codes: string[];
    potential_savings_low: number;
    potential_savings_high: number;
  }>,
  totalOvercharge: number
) {
  if (errors.length === 0) {
    return "No billing errors were detected, so a dispute letter is not required.";
  }

  // Extract metadata from bill
  let patientName = "[Patient Name]";
  let accountNumber = "[Account Number]";
  let facility = "[Healthcare Provider]";
  let dateOfService = "[Date of Service]";

  const lines = billText.split("\n");
  for (const line of lines) {
    if (line.toLowerCase().includes("patient:")) {
      patientName = line.split(":")[1]?.trim() || patientName;
    } else if (
      line.toLowerCase().includes("account") &&
      line.includes(":")
    ) {
      accountNumber = line.split(":")[1]?.trim() || accountNumber;
    } else if (line.toLowerCase().includes("date of service")) {
      dateOfService = line.split(":")[1]?.trim() || dateOfService;
    }
  }

  // First non-empty line is often the facility name
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith("-") && !trimmed.startsWith("=")) {
      facility = trimmed;
      break;
    }
  }

  const today = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  let letter = `${today}

${facility}
Billing Department
[Address Line 1]
[City, State ZIP]

Re: Formal Dispute of Medical Bill
Patient: ${patientName}
Account Number: ${accountNumber}
Date of Service: ${dateOfService}

Dear Billing Department,

I am writing to formally dispute charges on my medical bill referenced above. After careful review and comparison with standard Medicare rates and CMS billing guidelines, I have identified the following issues:

`;

  errors.forEach((error, index) => {
    letter += `${index + 1}. ${error.type.replace(/_/g, " ")}
   ${error.description}
   CPT Codes Affected: ${error.cpt_codes.join(", ")}
   Potential Overcharge: $${error.potential_savings_low.toFixed(2)} - $${error.potential_savings_high.toFixed(2)}

`;
  });

  letter += `Based on these findings, I estimate the total potential overcharge to be approximately $${totalOvercharge.toFixed(2)}.

I am requesting the following actions:
1. A detailed, itemized explanation of all charges
2. Correction of any billing errors identified above
3. An adjusted bill reflecting fair and appropriate charges

Under the No Surprises Act and applicable state patient billing protection laws, I am entitled to dispute these charges and receive a good faith estimate of costs. I request a written response within 30 business days.

If I do not receive a satisfactory response, I will escalate this matter to my state's insurance commissioner and the Centers for Medicare & Medicaid Services.

Sincerely,

${patientName}
[Your Address]
[Your Phone Number]
[Your Email]

Enclosures:
- Copy of original itemized bill
- This dispute letter
`;

  return letter;
}

export async function POST(request: NextRequest) {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      try {
        const body = await request.json();
        const billText = body.bill_text || "";

        if (!billText.trim()) {
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ type: "error", message: "No bill text provided" })}\n\n`
            )
          );
          controller.close();
          return;
        }

        // Simulate Triage step
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_start", step: "Triage" })}\n\n`
          )
        );
        await new Promise((resolve) => setTimeout(resolve, 800));
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_complete", step: "Triage", duration: 0.8 })}\n\n`
          )
        );

        // Simulate Parser step
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_start", step: "Parser" })}\n\n`
          )
        );
        await new Promise((resolve) => setTimeout(resolve, 600));
        const { charges, icdCodes } = parseBillText(billText);
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_complete", step: "Parser", duration: 0.6 })}\n\n`
          )
        );

        // Simulate Pricing step
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_start", step: "Pricing" })}\n\n`
          )
        );
        await new Promise((resolve) => setTimeout(resolve, 700));
        const pricingResults = calculatePricing(charges);
        const totalBilled = charges.reduce((sum, c) => sum + c.charge, 0);
        const totalFair = pricingResults.reduce(
          (sum, p) => sum + p.medicare_rate,
          0
        );
        const totalOvercharge = Math.max(totalBilled - totalFair, 0);
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_complete", step: "Pricing", duration: 0.7 })}\n\n`
          )
        );

        // Simulate Auditor step
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_start", step: "Auditor" })}\n\n`
          )
        );
        await new Promise((resolve) => setTimeout(resolve, 900));
        const errors = detectErrors(charges, pricingResults);
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "step_complete", step: "Auditor", duration: 0.9 })}\n\n`
          )
        );

        if (errors.length > 0) {
          // Simulate Researcher step
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ type: "step_start", step: "Researcher" })}\n\n`
            )
          );
          await new Promise((resolve) => setTimeout(resolve, 600));
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ type: "step_complete", step: "Researcher", duration: 0.6 })}\n\n`
            )
          );

          // Simulate Fact-Checker step
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ type: "step_start", step: "Fact-Checker" })}\n\n`
            )
          );
          await new Promise((resolve) => setTimeout(resolve, 500));
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ type: "step_complete", step: "Fact-Checker", duration: 0.5 })}\n\n`
            )
          );

          // Simulate Writer step
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ type: "step_start", step: "Writer" })}\n\n`
            )
          );
          await new Promise((resolve) => setTimeout(resolve, 800));
        }

        const disputeLetter = generateDisputeLetter(
          billText,
          errors,
          totalOvercharge
        );

        if (errors.length > 0) {
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({ type: "step_complete", step: "Writer", duration: 0.8 })}\n\n`
            )
          );
        }

        // Send final result
        const result = {
          session_id: crypto.randomUUID(),
          bill_text: billText,
          parsed_charges: charges,
          icd_codes: icdCodes,
          bill_metadata: {},
          pricing_results: pricingResults,
          total_billed: Math.round(totalBilled * 100) / 100,
          total_fair: Math.round(totalFair * 100) / 100,
          total_overcharge: Math.round(totalOvercharge * 100) / 100,
          errors_found: errors,
          error_count: errors.length,
          patient_rights: [],
          verified_rights: [],
          dispute_letter: disputeLetter,
          current_agent: "complete",
          status: "complete",
        };

        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "result", result })}\n\n`
          )
        );
      } catch (error) {
        console.error("Analysis error:", error);
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: "error", message: "Analysis failed" })}\n\n`
          )
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
