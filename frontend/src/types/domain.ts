// Single source of truth for the backend's enum shapes. There's no endpoint
// that exposes these, so they're mirrored by hand — see src/lib/enums.ts for
// the corresponding option lists used in <Select> components. Keep both in
// sync with app/models/schemas.py if the backend enums ever change.

export type DocumentStatus =
  | "processing"
  | "awaiting_approval"
  | "complete"
  | "rejected"
  | "failed"

export type FilingType = "10-K" | "10-Q" | "8-K" | "DEF 14A" | "other"

export type FiscalPeriod = "Q1" | "Q2" | "Q3" | "Q4" | "FY"

export type Severity = "info" | "warning" | "anomaly" | "critical"

export type FindingCategory =
  | "risk_factor"
  | "legal_proceeding"
  | "accounting_policy"
  | "governance"
  | "anomaly"
  | "other"

export type ReviewDecisionValue = "approve" | "reject"

export interface DocumentOut {
  id: string
  filename: string
  status: DocumentStatus
  company_id: string | null
  ticker: string | null
  company_name: string | null
  filing_type: FilingType | null
  fiscal_year: number | null
  fiscal_period: FiscalPeriod | null
  period_end_date: string | null
  created_at: string
  updated_at: string
}

export interface Finding {
  id: string
  document_id: string
  company_id: string | null
  category: FindingCategory
  field_name: string
  value: string | null
  severity: Severity
  confidence: number | null
  citation: string | null
  requires_approval: boolean
  created_at: string
}

export interface ReviewDecisionInput {
  decision: ReviewDecisionValue
  reason?: string | null
  reviewer?: string | null
}

export interface ReviewDecisionResult {
  document_id: string
  decision: ReviewDecisionInput
}
