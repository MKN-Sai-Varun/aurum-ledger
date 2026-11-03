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