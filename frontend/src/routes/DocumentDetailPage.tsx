import { useEffect } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { DecisionPanel } from "@/components/DecisionPanel"
import { DocumentMetaStrip } from "@/components/DocumentMetaStrip"
import { FindingsList } from "@/components/FindingsList"
import { StatusBadge } from "@/components/StatusBadge"
import { Skeleton } from "@/components/ui/skeleton"
import { useDocument } from "@/hooks/useDocument"
import { useFindings } from "@/hooks/useFindings"
import { ApiError } from "@/api/client"

export function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: document, isLoading, error } = useDocument(id)
  const { data: findings, isLoading: findingsLoading } = useFindings(id, document?.status)

  useEffect(() => {
    if (error instanceof ApiError && error.status === 404) {
      toast.error("Document not found.")
      navigate("/")
    }
  }, [error, navigate])

  if (isLoading || !document) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    )
  }

  return (
    <div>
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="size-3.5" />
        Back to filings
      </Link>

      <div className="flex items-center gap-3 mb-1">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          {document.ticker ?? document.filename}
        </h1>
        <StatusBadge status={document.status} />
      </div>
      <p className="text-sm text-muted-foreground mb-5">{document.filename}</p>

      <DocumentMetaStrip document={document} />

      {document.status === "processing" && (
        <div className="flex items-center gap-2 text-sm text-status-processing bg-status-processing-bg rounded-lg px-4 py-3 my-6">
          <Loader2 className="size-4 animate-spin" />
          Reviewing filing — this can take up to a minute.
        </div>
      )}

      {document.status === "awaiting_approval" && (
        <div className="my-6">
          <DecisionPanel documentId={document.id} />
        </div>
      )}

      <div className="mt-8">
        <h2 className="text-sm font-semibold text-foreground mb-3">Findings</h2>
        <FindingsList findings={findings} isLoading={findingsLoading} />
      </div>
    </div>
  )
}
