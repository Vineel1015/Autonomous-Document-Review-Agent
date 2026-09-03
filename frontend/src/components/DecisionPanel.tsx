import { useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { Check, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { useSubmitDecision } from "@/hooks/useSubmitDecision"
import type { ReviewDecisionValue } from "@/types/domain"

export function DecisionPanel({ documentId }: { documentId: string }) {
  const [pending, setPending] = useState<ReviewDecisionValue | null>(null)
  const [reason, setReason] = useState("")
  const [reviewer, setReviewer] = useState("")
  const [reasonError, setReasonError] = useState(false)
  const { mutate, isPending } = useSubmitDecision(documentId)

  function startDecision(decision: ReviewDecisionValue) {
    setPending(decision)
    setReasonError(false)
  }

  function cancel() {
    setPending(null)
    setReasonError(false)
  }

  function submit() {
    if (pending === "reject" && reason.trim() === "") {
      setReasonError(true)
      return
    }
    mutate(
      { decision: pending as ReviewDecisionValue, reason: reason.trim() || null, reviewer: reviewer.trim() || null },
      { onSuccess: () => setPending(null) },
    )
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="rounded-lg border border-status-awaiting/30 bg-status-awaiting-bg/30 p-5"
    >
      <h3 className="text-sm font-semibold text-foreground mb-1">Review decision required</h3>
      <p className="text-sm text-muted-foreground mb-4">
        This filing has findings that need a human sign-off before it can be finalized.
      </p>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={pending ?? "idle"}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 4 }}
          transition={{ duration: 0.15, ease: "easeOut" }}
        >
          {pending === null ? (
          <div className="flex gap-2">
            <Button onClick={() => startDecision("approve")} className="gap-1.5">
              <Check className="size-4" />
              Approve
            </Button>
            <Button onClick={() => startDecision("reject")} variant="outline" className="gap-1.5">
              <X className="size-4" />
              Reject
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <Label htmlFor="decision-reason" className="mb-1.5">
                Reason{pending === "reject" ? "" : " (optional)"}
              </Label>
              <Textarea
                id="decision-reason"
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value)
                  if (reasonError) setReasonError(false)
                }}
                placeholder={pending === "reject" ? "Why is this being rejected?" : "Any context for the record..."}
                rows={3}
                aria-invalid={reasonError}
              />
              {reasonError && (
                <p className="text-xs text-destructive mt-1">A reason is required to reject a filing.</p>
              )}
            </div>
            <div>
              <Label htmlFor="decision-reviewer" className="mb-1.5">
                Reviewer (optional)
              </Label>
              <Input
                id="decision-reviewer"
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
                placeholder="Your name or email"
              />
            </div>
            <div className="flex gap-2 pt-1">
              <Button onClick={submit} disabled={isPending}>
                {isPending ? "Submitting..." : `Confirm ${pending === "approve" ? "approval" : "rejection"}`}
              </Button>
              <Button onClick={cancel} variant="ghost" disabled={isPending}>
                Cancel
              </Button>
            </div>
          </div>
        )}
        </motion.div>
      </AnimatePresence>
    </motion.div>
  )
}
