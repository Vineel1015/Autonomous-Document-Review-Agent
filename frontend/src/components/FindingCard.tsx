import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { motion } from "framer-motion"
import { CategoryTag } from "@/components/CategoryTag"
import { SeverityBadge } from "@/components/SeverityBadge"
import { cn } from "@/lib/utils"
import type { Finding } from "@/types/domain"

const CITATION_COLLAPSE_LENGTH = 220

export function FindingCard({ finding }: { finding: Finding }) {
  const [citationOpen, setCitationOpen] = useState(false)
  const citation = finding.citation
  const citationIsLong = (citation?.length ?? 0) > CITATION_COLLAPSE_LENGTH

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "rounded-lg border bg-card p-5",
        finding.requires_approval ? "border-severity-critical/30" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <SeverityBadge severity={finding.severity} />
        <CategoryTag category={finding.category} />
        {finding.requires_approval && (
          <span className="text-xs font-medium text-severity-critical">Needs approval</span>
        )}
        {finding.confidence !== null && (
          <span className="text-xs text-muted-foreground ml-auto">
            {Math.round(finding.confidence * 100)}% confidence
          </span>
        )}
      </div>

      <h3 className="text-sm font-semibold text-foreground mb-1.5">{finding.field_name}</h3>

      {finding.value && (
        <p className="text-sm text-foreground/90 leading-relaxed max-w-[70ch]">{finding.value}</p>
      )}

      {citation && (
        <div className="mt-4">
          <blockquote
            className={cn(
              "border-l-2 border-border pl-3 text-sm text-muted-foreground italic",
              citationIsLong && !citationOpen && "line-clamp-3",
            )}
          >
            {citation}
          </blockquote>
          {citationIsLong && (
            <button
              type="button"
              onClick={() => setCitationOpen((open) => !open)}
              className="flex items-center gap-1 text-xs text-primary mt-1.5 hover:underline"
            >
              <ChevronDown className={cn("size-3 transition-transform", citationOpen && "rotate-180")} />
              {citationOpen ? "Show less" : "Show full citation"}
            </button>
          )}
        </div>
      )}
    </motion.div>
  )
}
