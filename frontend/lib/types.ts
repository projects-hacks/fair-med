// Agent workflow types
export type AgentName = 
  | "triage" 
  | "parser" 
  | "pricing" 
  | "auditor" 
  | "researcher" 
  | "factchecker" 
  | "writer";

export type AgentStatus = "idle" | "running" | "complete" | "error" | "skipped";

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  output?: string;
  timestamp: string;
}

export interface AgentEvent {
  agent: AgentName;
  status: AgentStatus;
  reasoning?: string;
  tool_calls?: ToolCall[];
  output?: Record<string, unknown>;
  error?: string;
  timestamp: string;
}

// Bill analysis types
export interface ParsedCharge {
  cpt_code: string;
  description: string;
  quantity: number;
  billed_amount: number;
  date_of_service?: string;
}

export interface PricingResult {
  cpt_code: string;
  description: string;
  billed_amount: number;
  medicare_rate: number;
  fair_estimate: number;
  difference: number;
  difference_percent: number;
}

export interface BillingError {
  type: "duplicate" | "upcoding" | "unbundling" | "overcharge" | "other";
  severity: "low" | "medium" | "high";
  description: string;
  cpt_codes: string[];
  potential_savings: number;
  evidence?: string;
}

export interface AnalysisResult {
  session_id: string;
  status: "complete" | "error";
  total_billed: number;
  total_fair: number;
  total_overcharge: number;
  error_count: number;
  parsed_charges: ParsedCharge[];
  pricing_results: PricingResult[];
  audit_findings: BillingError[];
  agents_used: AgentName[];
}

export interface DisputeLetterStatus {
  session_id: string;
  status: "pending" | "generating" | "ready" | "error";
  download_url?: string;
  error?: string;
}

// SSE event types from backend
export interface SSEEvent {
  type: "agent_start" | "agent_reasoning" | "agent_tool_call" | "agent_complete" | "agent_error" | "analysis_complete";
  data: AgentEvent | AnalysisResult;
}
