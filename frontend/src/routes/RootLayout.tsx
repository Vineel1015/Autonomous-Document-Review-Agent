import { Link, Outlet } from "react-router-dom"
import { FileSearch } from "lucide-react"

// Future auth seam: an auth-guard wrapper (redirect to /login if unauthenticated)
// slots in around <Outlet /> here once auth exists — this layout doesn't need
// to change shape for that, just gain a wrapping condition.
export function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center">
          <Link to="/" className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <FileSearch className="size-4 text-primary" />
            Document Review Agent
          </Link>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-10">
        <Outlet />
      </main>
    </div>
  )
}
