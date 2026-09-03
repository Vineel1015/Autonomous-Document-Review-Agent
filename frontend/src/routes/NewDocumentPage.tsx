import { Link } from "react-router-dom"
import { ArrowLeft } from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { UploadForm } from "@/components/UploadForm"

export function NewDocumentPage() {
  return (
    <div>
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="size-3.5" />
        Back to filings
      </Link>
      <PageHeader
        title="Upload Filing"
        description="Submit a 10-K or 10-Q for extraction and review."
      />
      <UploadForm />
    </div>
  )
}
