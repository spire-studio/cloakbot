import { Shield } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Chip } from '@/overlays/privacy/lib/ui'
import { usePrivacyState } from '@/overlays/privacy/context/PrivacyStateProvider'

/**
 * Compact privacy summary row for the agent activity cluster.
 *
 * Shows, **for this cluster's own privacy turn** (``turnId``), how many entities
 * were placeholdered, how many tool outputs were sanitized, and the pipeline
 * duration — so the privacy pass reads as a first-class step in the activity
 * timeline rather than an invisible side-effect. ``turnId`` is the privacy turn
 * the cluster's assistant reply carries (``UIMessage.privacyTurnId``); without it
 * (a turn with no privacy activity) the row renders nothing. Falls back to the
 * latest turn only when no ``turnId`` is supplied (legacy callers).
 */
export function PrivacyTraceRow({ turnId, className }: { turnId?: string; className?: string }) {
  const { turns, timelinesByTurnId } = usePrivacyState()
  const turn = turnId ? turns.find((t) => t.turnId === turnId) : undefined
  if (!turn) return null

  const sanitizedToolCount = (turn.toolResults ?? []).filter((r) => r.wasSanitized).length
  const placeholderCount = (turn.remotePrompt.match(/<<[A-Z0-9_]+>>/g) ?? []).length
  const timeline = timelinesByTurnId[turn.turnId]
  const durationMs = timeline?.totalDurationMs

  return (
    <div
      data-testid="privacy-trace-row"
      className={cn(
        'flex flex-wrap items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground',
        className,
      )}
    >
      <Shield className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="font-medium text-foreground">Privacy</span>
      {placeholderCount > 0 && <Chip>{placeholderCount} placeholdered</Chip>}
      {sanitizedToolCount > 0 && <Chip>{sanitizedToolCount} tool outputs sanitized</Chip>}
      {typeof durationMs === 'number' && (
        <span className="tabular-nums text-muted-foreground/70">{durationMs} ms</span>
      )}
    </div>
  )
}
