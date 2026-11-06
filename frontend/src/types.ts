export type CaseStatus = "pending_review" | "approved" | "rejected";
export type Priority = "high" | "medium" | "low";

export interface Transaction {
  tx_id: number;
  time_step: number;
  label: string;
  risk_score: number;
  flagged?: boolean;
}

export interface CaseSummary {
  case_id: string;
  status: CaseStatus;
  priority: Priority;
  summary: string;
  recommended_action: string;
  created_at: string | null;
  decided_at: string | null;
  transaction: Transaction;
}

export interface CaseDetail extends CaseSummary {
  key_indicators: string[] | null;
  narrative: string;
  unsupported_ids: number[] | null;
  drafted_by: string;
  decided_by: string | null;
  decision_note: string | null;
}

export interface GraphNodeData {
  id: string;
  label: string;
  risk_score: number;
  flagged: boolean;
  dataset_label: string;
  is_case: boolean;
}

export interface GraphElements {
  nodes: { data: GraphNodeData }[];
  edges: { data: { id: string; source: string; target: string } }[];
}

export interface InvestigateResult {
  tx_id: number;
  case_id?: string;
  priority?: Priority;
  summary?: string;
  evidence_check_passed?: boolean;
  error?: string;
}
