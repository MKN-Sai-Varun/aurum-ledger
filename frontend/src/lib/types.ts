export type Role = "issue_clerk" | "finance_head";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
}

export interface Wastage {
  category_id: number;
  category: string;
  wastage_pct: string;
}

export interface Karigar {
  id: number;
  name: string;
  is_active: boolean;
  open_jobs: number;
  wastage: Wastage[];
}

export const ROLE_LABEL: Record<Role, string> = {
  issue_clerk: "Issue clerk",
  finance_head: "Finance head",
};
export interface Category {
  id: number;
  name: string;
}

export interface Slip {
  txn_no: string;
  job_no: string;
  entry_date: string;
  karigar_id: number;
  karigar: string;
  category: string;
  gross_weight_g: string;
  purity_pct: string;
  fine_weight_g: string;
  allowed_wastage_pct: string;
  allowed_wastage_g: string;
  balance_g: string;
  note: string | null;
  issued_by: string;
}

export interface Job {
  job_no: string;
  karigar_id: number;
  karigar: string;
  category: string;
  status: "OPEN" | "CLOSED";
  opened_on: string;
  closed_on: string | null;
  issued_fine_g: string;
  returned_fine_g: string;
  outstanding_g: string;
  allowed_wastage_pct: string;
  allowed_wastage_g: string;
  unexplained_g: string | null;
  review: boolean | null;
}

export interface ReceiptResult {
  txn_no: string;
  kind: string;
  entry_date: string;
  gross_weight_g: string;
  purity_pct: string;
  fine_weight_g: string;
  huid: string | null;
  note: string | null;
  job: Job;
}

export const KIND_LABEL: Record<string, string> = {
  ISSUE: "Issue",
  RECEIPT_PIECE: "Finished piece",
  RECEIPT_SCRAP: "Scrap",
  RECEIPT_FILINGS: "Filings",
  REVERSAL: "Reversal",
};

export interface LedgerRow {
  txn_no: string;
  entry_date: string;
  job_no: string;
  kind: string;
  gross_weight_g: string;
  purity_pct: string;
  fine_weight_g: string;
  change_g: string;
  balance_g: string;
  huid: string | null;
  note: string | null;
  reverses: string | null;
  reversed_by: string | null;
}

export interface LedgerData {
  karigar_id: number;
  karigar: string;
  opening_balance_g: string;
  closing_balance_g: string;
  entries: LedgerRow[];
  truncated: boolean;
}

export interface ReversalResult {
  txn_no: string;
  reverses_txn_no: string;
  change_g: string;
}

export interface AlertFigure {
  label: string;
  value: string;
}

export interface AlertItem {
  id: string;
  kind: string;
  karigar_id: number;
  karigar: string;
  job_no: string | null;
  title: string;
  message: string;
  figures: AlertFigure[];
}

export interface AlertsData {
  drift_count: number;
  review_count: number;
  rules: string[];
  alerts: AlertItem[];
}

export interface Holder {
  karigar_id: number;
  karigar: string;
  balance_g: string;
}

export interface Statement {
  as_of: string;
  total_g: string;
  vault_g: string;
  karigars_g: string;
  refiner_g: string;
  consistent: boolean;
  basis: string;
  holders: Holder[];
}

export interface StockMove {
  id: number;
  entry_date: string;
  kind: string;
  label: string;
  fine_weight_g: string;
  note: string | null;
  by: string;
}

export interface ReadingCorrection {
  txn_no: string | null;
  target: string;
  read_value: string | null;
  entered_value: string | null;
  reason: string | null;
  by: string;
  at: string | null;
}

export interface ReadingsSummaryData {
  total: number;
  accepted: number;
  corrected: number;
  unused: number;
  unreadable: number;
  correction_rate_pct: string | null;
  by_source: Record<string, number>;
  recent_corrections: ReadingCorrection[];
}