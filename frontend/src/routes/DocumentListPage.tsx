import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { FileText, Plus } from "lucide-react"
import { EmptyState } from "@/components/EmptyState"
import { PageHeader } from "@/components/PageHeader"
import { StatusBadge } from "@/components/StatusBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useDocumentList } from "@/hooks/useDocumentList"
import { fiscalPeriodLabel, relativeTime } from "@/lib/formatters"
import type { DocumentStatus } from "@/types/domain"

const FILTERS: { label: string; value: DocumentStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Awaiting Approval", value: "awaiting_approval" },
  { label: "Processing", value: "processing" },
  { label: "Complete", value: "complete" },
  { label: "Rejected", value: "rejected" },
  { label: "Failed", value: "failed" },
]

export function DocumentListPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<DocumentStatus | "all">("all")
  const { data: documents, isLoading } = useDocumentList(
    filter === "all" ? {} : { status: filter },
  )
  // A cheap, separate unfiltered count just for the "needs review" badge —
  // avoids the badge count changing meaning depending on the active filter.
  const { data: allDocuments } = useDocumentList({})
  const needsReviewCount = allDocuments?.filter((d) => d.status === "awaiting_approval").length ?? 0

  return (
    <div>
      <PageHeader
        title="Filings"
        description="Review queue for submitted SEC filings."
        actions={
          <Button asChild>
            <Link to="/documents/new" className="gap-1.5">
              <Plus className="size-4" />
              Upload Filing
            </Link>
          </Button>
        }
      />

      <div className="flex items-center gap-1 mb-6 flex-wrap">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f.value
                ? "bg-secondary text-secondary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {f.label}
            {f.value === "awaiting_approval" && needsReviewCount > 0 && (
              <Badge className="bg-status-awaiting-bg text-status-awaiting border-transparent h-4 px-1.5">
                {needsReviewCount}
              </Badge>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12 rounded-md" />
          ))}
        </div>
      ) : !documents || documents.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No filings yet"
          description="Upload a 10-K or 10-Q to start a review."
          action={
            <Button asChild>
              <Link to="/documents/new">Upload Filing</Link>
            </Button>
          }
        />
      ) : (
        <div className="border border-border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Filing</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Period</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Submitted</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.map((doc) => (
                <TableRow
                  key={doc.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/documents/${doc.id}`)}
                >
                  <TableCell className="font-medium text-foreground">{doc.filename}</TableCell>
                  <TableCell>{doc.ticker ?? "—"}</TableCell>
                  <TableCell>{doc.filing_type ?? "—"}</TableCell>
                  <TableCell>{fiscalPeriodLabel(doc.fiscal_year, doc.fiscal_period)}</TableCell>
                  <TableCell>
                    <StatusBadge status={doc.status} />
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground" title={doc.created_at}>
                    {relativeTime(doc.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
