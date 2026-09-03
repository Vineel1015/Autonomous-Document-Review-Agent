// The single point every API call passes through. This is deliberately where
// a future `Authorization: Bearer <token>` header gets added once auth
// exists — see the commented block below — so no other file needs to change
// when that lands.

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `Request failed with status ${status}`)
    this.status = status
    this.detail = detail
    this.name = "ApiError"
  }
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && init?.body) {
    headers.set("Content-Type", "application/json")
  }

  // Future auth seam:
  // const token = getAuthToken()
  // if (token) headers.set("Authorization", `Bearer ${token}`)

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers })

  if (!response.ok) {
    let detail: unknown = null
    try {
      detail = await response.json()
    } catch {
      // body wasn't JSON — leave detail null, status code still tells the caller enough
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    }),
}
