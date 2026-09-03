import { useQuery } from "@tanstack/react-query"
import { listDocuments, type ListDocumentsParams } from "@/api/documents"
import type { DocumentOut } from "@/types/domain"

export function useDocumentList(params: ListDocumentsParams = {}) {
  return useQuery<DocumentOut[]>({
    queryKey: ["documents", params],
    queryFn: () => listDocuments(params),
    refetchInterval: (query) => {
      const rows = query.state.data
      const anyProcessing = rows?.some((d) => d.status === "processing")
      return anyProcessing ? 5000 : false
    },
  })
}
