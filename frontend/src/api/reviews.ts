import { apiClient } from "@/api/client"
import type { Finding, ReviewDecisionInput, ReviewDecisionResult } from "@/types/domain"

export function getFindings(documentId: string): Promise<Finding[]> {
  return apiClient.get<Finding[]>(`/reviews/${documentId}/findings`)
}

export function submitDecision(
  documentId: string,
  decision: ReviewDecisionInput,
): Promise<ReviewDecisionResult> {
  return apiClient.post<ReviewDecisionResult>(`/reviews/${documentId}/decision`, decision)
}
