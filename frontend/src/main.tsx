import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "react-router-dom"
import { Toaster } from "@/components/ui/sonner"
import { queryClient } from "@/lib/queryClient"
import { router } from "@/router"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* Opt into v7's rendering behavior early (v6 supports this via a
          future flag) — silences the console warning without pulling in
          v7's package version and its SSR/open-redirect CVEs, which don't
          apply to this app's static-route, non-SSR usage anyway. */}
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
      <Toaster position="top-right" />
    </QueryClientProvider>
  </StrictMode>,
)
