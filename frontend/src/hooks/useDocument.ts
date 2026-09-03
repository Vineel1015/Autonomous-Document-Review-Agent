import { useQuery } from "@tanstack/react-query"
import { getDocument } from "@/api/documents"
import type { DocumentOut } from "@/types/domain"

// The crux of the whole app's UX: poll fast while the LangGraph review is
// actively running, slower while it's waiting on a human, and stop entirely
// once it's in a terminal state. There's no websocket/SSE backend — this is
// the only way the UI finds out a background run has progressed.
export function useDocument(id: string | undefined) {
  return useQuery<DocumentOut>({
    queryKey: ["document", id],
    queryFn: () => getDocument(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === "processing") return 3000
      if (status === "awaiting_approval") return 8000
      return false
    },
  })
}
