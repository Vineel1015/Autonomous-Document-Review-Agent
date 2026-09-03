import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ApiError } from "@/api/client"
import { submitDecision } from "@/api/reviews"
import type { ReviewDecisionInput } from "@/types/domain"

export function useSubmitDecision(documentId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: ReviewDecisionInput) => submitDecision(documentId, input),
    onSuccess: (result) => {
      toast.success(
        result.decision.decision === "approve" ? "Filing approved" : "Filing rejected",
      )
      // No optimistic status flip — the LangGraph resume is server-authoritative
      // and non-instant. Invalidate and let polling (useDocument/useFindings)
      // carry the UI to the next state naturally.
      queryClient.invalidateQueries({ queryKey: ["document", documentId] })
      queryClient.invalidateQueries({ queryKey: ["findings", documentId] })
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        // Expected concurrency case, not a real error: someone else already
        // decided, or the pause resolved on its own. Invalidate so the
        // decision panel disappears once the real status is known (it's
        // conditionally rendered on status === "awaiting_approval").
        toast.info("This document was already reviewed elsewhere.")
        queryClient.invalidateQueries({ queryKey: ["document", documentId] })
        return
      }
      if (error instanceof ApiError && error.status === 404) {
        toast.error("Document not found.")
        return
      }
      toast.error("Couldn't submit the decision. Please try again.")
    },
  })
}
