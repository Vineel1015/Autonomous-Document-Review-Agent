import { formatDistanceToNow, parseISO } from "date-fns"
import type { DocumentStatus, FiscalPeriod, Severity } from "@/types/domain"

export function relativeTime(iso: string): string {
  return formatDistanceToNow(parseISO(iso), { addSuffix: true })
}

export function fiscalPeriodLabel(year: number | null, period: FiscalPeriod | null): string {
  if (!year) return "—"
  if (!period || period === "FY") return `FY${year}`
  return `FY${year} · ${period}`
}

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  processing: "Processing",
  awaiting_approval: "Awaiting Approval",
  complete: "Complete",
  rejected: "Rejected",
  failed: "Failed",
}

export const SEVERITY_LABELS: Record<Severity, string> = {
  info: "Info",
  warning: "Warning",
  anomaly: "Anomaly",
  critical: "Critical",
}
