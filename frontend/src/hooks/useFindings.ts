import { useQuery } from "@tanstack/react-query"
import { getFindings } from "@/api/reviews"
import type { DocumentStatus, Finding } from "@/types/domain"

// Mirrors useDocument's polling schedule (passed the document's current
// status rather than owning its own timer) so findings and status refresh
// in lockstep — a new finding never lags behind a status change on screen.
export function useFindings(documentId: string | undefined, documentStatus: DocumentStatus | undefined) {
  return useQuery<Finding[]>({
    queryKey: ["findings", documentId],
    queryFn: () => getFindings(documentId as string),
    enabled: Boolean(documentId),
    refetchInterval: () => {
      if (documentStatus === "processing") return 3000
      if (documentStatus === "awaiting_approval") return 8000
      return false
    },
  })
}
