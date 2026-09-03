import { Badge } from "@/components/ui/badge"
import type { FindingCategory } from "@/types/domain"

const LABELS: Record<FindingCategory, string> = {
  risk_factor: "Risk Factor",
  legal_proceeding: "Legal Proceeding",
  accounting_policy: "Accounting Policy",
  governance: "Governance",
  anomaly: "Anomaly",
  other: "Other",
}

export function CategoryTag({ category }: { category: FindingCategory }) {
  return (
    <Badge variant="secondary" className="font-normal">
      {LABELS[category]}
    </Badge>
  )
}
