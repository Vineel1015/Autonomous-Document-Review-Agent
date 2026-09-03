// Hardcoded to match app/models/schemas.py's enums — no endpoint exposes
// these, so this file needs a manual update if the backend enums change.
import type { DocumentStatus, FilingType, FiscalPeriod, Severity } from "@/types/domain"

export const FILING_TYPES: { value: FilingType; label: string }[] = [
  { value: "10-K", label: "10-K" },
  { value: "10-Q", label: "10-Q" },
  { value: "8-K", label: "8-K" },
  { value: "DEF 14A", label: "DEF 14A" },
  { value: "other", label: "Other" },
]

export const FISCAL_PERIODS: { value: FiscalPeriod; label: string }[] = [
  { value: "Q1", label: "Q1" },
  { value: "Q2", label: "Q2" },
  { value: "Q3", label: "Q3" },
  { value: "Q4", label: "Q4" },
  { value: "FY", label: "Full Year" },
]

export const DOCUMENT_STATUSES: { value: DocumentStatus; label: string }[] = [
  { value: "processing", label: "Processing" },
  { value: "awaiting_approval", label: "Awaiting Approval" },
  { value: "complete", label: "Complete" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
]

// Escalation order — used to sort findings critical-first.
export const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  anomaly: 1,
  warning: 2,
  info: 3,
}
