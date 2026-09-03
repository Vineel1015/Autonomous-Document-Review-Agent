import { FindingCard } from "@/components/FindingCard"
import { Skeleton } from "@/components/ui/skeleton"
import { SEVERITY_ORDER } from "@/lib/enums"
import type { Finding } from "@/types/domain"

export function FindingsList({ findings, isLoading }: { findings: Finding[] | undefined; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28 rounded-lg" />
        ))}
      </div>
    )
  }

  if (!findings || findings.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center border border-dashed border-border rounded-lg">
        No findings yet.
      </p>
    )
  }

  const sorted = [...findings].sort((a, b) => {
    const bySeverity = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
    if (bySeverity !== 0) return bySeverity
    return a.created_at.localeCompare(b.created_at)
  })

  return (
    <div className="space-y-3">
      {sorted.map((finding) => (
        <FindingCard key={finding.id} finding={finding} />
      ))}
    </div>
  )
}
