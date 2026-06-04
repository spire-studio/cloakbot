import { ShieldAlert } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Chip, GhostButton } from '@/overlays/privacy/lib/ui'
import { severityClasses } from '@/overlays/privacy/lib/severity'
import { usePrivacyState } from '@/overlays/privacy/context/PrivacyStateProvider'
import type { ToolApproval } from '@/overlays/privacy/types'

type ResolveHandler = (approvalId: string, approved: boolean) => void

/**
 * Human-in-the-loop approval card for a pending tool call.
 *
 * The backend emits a gated ``tool_approval`` frame whenever a non-LOCAL,
 * HIGH-severity tool needs explicit consent before its (locally-restored)
 * arguments run. This card shows the remote (placeholdered) arguments and lets
 * the user approve or deny; the reply rides the inbound ``tool_approval``
 * envelope (``onResolve``).
 *
 * Privacy: ``remoteArguments`` are already placeholdered (safe to display);
 * ``restoredArguments`` are localhost-only and are intentionally NOT shown here
 * (they are stripped server-side for non-localhost peers anyway).
 */
export function ToolApprovalPrompt({
  approval,
  onResolve,
}: {
  approval: ToolApproval
  onResolve: ResolveHandler
}) {
  if (approval.status !== 'pending') return null

  const highSeverity = approval.detectedEntities.filter((e) => e.severity === 'high').length

  return (
    <div
      data-testid="tool-approval-prompt"
      className="space-y-3 rounded-xl border border-amber-300/70 bg-amber-50/70 p-4 dark:border-amber-500/40 dark:bg-amber-500/10"
    >
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 text-amber-700 dark:text-amber-300" aria-hidden />
        <div className="text-sm font-semibold text-foreground">Approval required</div>
        <Chip className={cn(severityClasses('high'))}>{approval.privacyClass}</Chip>
      </div>
      <p className="text-[13px] leading-[1.5] text-muted-foreground">
        <span className="font-medium text-foreground">{approval.toolName}</span> wants to run with arguments derived
        from {approval.detectedEntities.length} detected
        {approval.detectedEntities.length === 1 ? ' entity' : ' entities'}
        {highSeverity > 0 ? ` (${highSeverity} high-severity)` : ''}.
      </p>
      <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 px-3 py-2 font-mono text-[11px] leading-5 text-muted-foreground">
        {JSON.stringify(approval.remoteArguments, null, 2)}
      </pre>
      <div className="flex items-center justify-end gap-2">
        <GhostButton
          className="border border-border px-3 py-1.5"
          onClick={() => onResolve(approval.approvalId, false)}
          aria-label={`Deny ${approval.toolName}`}
        >
          Deny
        </GhostButton>
        <GhostButton
          className="border border-emerald-400/60 bg-emerald-100/60 px-3 py-1.5 text-emerald-800 hover:bg-emerald-200/60 dark:bg-emerald-500/15 dark:text-emerald-200"
          onClick={() => onResolve(approval.approvalId, true)}
          aria-label={`Approve ${approval.toolName}`}
        >
          Approve
        </GhostButton>
      </div>
    </div>
  )
}

/**
 * Renders the pending approval queue from privacy state.
 *
 * Mounted in the thread; resolves each pending approval through *onResolve*
 * (wired to the client's ``tool_approval`` inbound envelope at the call site).
 */
export function PendingToolApprovals({ onResolve }: { onResolve: ResolveHandler }) {
  const { approvals } = usePrivacyState()
  const pending = approvals.filter((a) => a.status === 'pending')
  if (pending.length === 0) return null
  return (
    <div className="space-y-3">
      {pending.map((approval) => (
        <ToolApprovalPrompt key={approval.approvalId} approval={approval} onResolve={onResolve} />
      ))}
    </div>
  )
}
