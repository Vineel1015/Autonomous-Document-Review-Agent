import { fiscalPeriodLabel, relativeTime } from "@/lib/formatters"
import type { DocumentOut } from "@/types/domain"

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-foreground">{value}</span>
    </div>
  )
}

export function DocumentMetaStrip({ document }: { document: DocumentOut }) {
  return (
    <div className="flex flex-wrap gap-x-8 gap-y-4 py-5 border-y border-border">
      <Item label="Company" value={document.ticker ?? "—"} />
      <Item label="Filing Type" value={document.filing_type ?? "—"} />
      <Item label="Period" value={fiscalPeriodLabel(document.fiscal_year, document.fiscal_period)} />
      <Item
        label="Period End"
        value={document.period_end_date ? document.period_end_date : "—"}
      />
      <Item label="Submitted" value={relativeTime(document.created_at)} />
    </div>
  )
}
