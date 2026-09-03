import { motion, AnimatePresence } from "framer-motion"
import { AlertTriangle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { STATUS_LABELS } from "@/lib/formatters"
import { cn } from "@/lib/utils"
import type { DocumentStatus } from "@/types/domain"

const STYLES: Record<DocumentStatus, string> = {
  processing: "bg-status-processing-bg text-status-processing",
  awaiting_approval: "bg-status-awaiting-bg text-status-awaiting",
  complete: "bg-status-complete-bg text-status-complete",
  rejected: "bg-status-rejected-bg text-status-rejected",
  failed: "bg-status-failed-bg text-status-failed",
}

export function StatusBadge({ status, className }: { status: DocumentStatus; className?: string }) {
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={status}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="inline-flex"
      >
        <Badge variant="outline" className={cn("border-transparent gap-1.5", STYLES[status], className)}>
          {status === "processing" && (
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-processing opacity-75" />
              <span className="relative inline-flex size-1.5 rounded-full bg-status-processing" />
            </span>
          )}
          {status === "failed" && <AlertTriangle className="size-3" />}
          {STATUS_LABELS[status]}
        </Badge>
      </motion.span>
    </AnimatePresence>
  )
}
