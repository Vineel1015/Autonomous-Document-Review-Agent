import { Badge } from "@/components/ui/badge"
import { SEVERITY_LABELS } from "@/lib/formatters"
import { cn } from "@/lib/utils"
import type { Severity } from "@/types/domain"

const STYLES: Record<Severity, string> = {
  info: "bg-severity-info-bg text-severity-info",
  warning: "bg-severity-warning-bg text-severity-warning",
  anomaly: "bg-severity-anomaly-bg text-severity-anomaly",
  critical: "bg-severity-critical-bg text-severity-critical",
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <Badge variant="outline" className={cn("border-transparent", STYLES[severity], className)}>
      {SEVERITY_LABELS[severity]}
    </Badge>
  )
}
