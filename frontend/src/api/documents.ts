import { apiClient } from "@/api/client"
import type { DocumentOut, DocumentStatus, FilingType, FiscalPeriod } from "@/types/domain"

export interface ListDocumentsParams {
  status?: DocumentStatus
  ticker?: string
  filing_type?: FilingType
  limit?: number
  offset?: number
}

export function listDocuments(params: ListDocumentsParams = {}): Promise<DocumentOut[]> {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const qs = search.toString()
  return apiClient.get<DocumentOut[]>(`/documents${qs ? `?${qs}` : ""}`)
}

export function getDocument(id: string): Promise<DocumentOut> {
  return apiClient.get<DocumentOut>(`/documents/${id}`)
}

export interface CreateDocumentInput {
  file: File
  ticker: string
  filing_type: FilingType
  fiscal_year: number
  fiscal_period: FiscalPeriod
  period_end_date?: string | null
}

export function createDocument(input: CreateDocumentInput): Promise<DocumentOut> {
  const form = new FormData()
  form.set("file", input.file)
  form.set("ticker", input.ticker)
  form.set("filing_type", input.filing_type)
  form.set("fiscal_year", String(input.fiscal_year))
  form.set("fiscal_period", input.fiscal_period)
  if (input.period_end_date) form.set("period_end_date", input.period_end_date)
  return apiClient.post<DocumentOut>("/documents", form)
}
