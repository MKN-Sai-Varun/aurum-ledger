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