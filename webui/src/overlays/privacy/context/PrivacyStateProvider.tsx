// Context module: Provider + consumer hooks are co-located (the canonical
// React context export shape). Upstream's eslint has no react-refresh plugin,
// so no fast-refresh suppression directive is needed here.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { onPrivacy, type PrivacyEvent, type PrivacyLaneClient } from '@/overlays/privacy/lib/privacy-client-lane'
import {
  EMPTY_SNAPSHOT,
  type PrivacyAnnotation,
  type PrivacySnapshot,
  type PrivacyTimeline,
  type PrivacyTurn,
  type ToolApproval,
} from '@/overlays/privacy/types'

export type PrivacyHeaderStats = {
  totalEntities: number
  highSeverityCount: number
  blockedSpans: number
}

type PrivacyStateValue = {
  snapshot: PrivacySnapshot
  turns: PrivacyTurn[]
  timelinesByTurnId: Record<string, PrivacyTimeline | undefined>
  /** Restoration annotations keyed by the assistant message id they belong to. */
  annotationsByReplyTo: Record<string, PrivacyAnnotation[]>
  approvals: ToolApproval[]
  stats: PrivacyHeaderStats
}

const EMPTY_STATE: PrivacyStateValue = {
  snapshot: EMPTY_SNAPSHOT,
  turns: [],
  timelinesByTurnId: {},
  annotationsByReplyTo: {},
  approvals: [],
  stats: { totalEntities: 0, highSeverityCount: 0, blockedSpans: 0 },
}

const PrivacyStateContext = createContext<PrivacyStateValue>(EMPTY_STATE)

function computeStats(snapshot: PrivacySnapshot, turns: PrivacyTurn[]): PrivacyHeaderStats {
  const highSeverityCount = snapshot.entities.filter((e) => e.severity === 'high').length
  // "Blocked spans" = every restored placeholder occurrence across remote
  // prompts (a proxy for "private values kept off the wire this session").
  const blockedSpans = turns.reduce((sum, turn) => {
    const matches = turn.remotePrompt.match(/<<[A-Z0-9_]+>>/g)
    return sum + (matches ? matches.length : 0)
  }, snapshot.total_entities)
  return { totalEntities: snapshot.total_entities, highSeverityCount, blockedSpans }
}

function mergeTurn(turns: PrivacyTurn[], turn: PrivacyTurn): PrivacyTurn[] {
  const index = turns.findIndex((t) => t.turnId === turn.turnId)
  if (index === -1) return [...turns, turn]
  const next = [...turns]
  next[index] = turn
  return next
}

function mergeApproval(approvals: ToolApproval[], approval: ToolApproval): ToolApproval[] {
  const index = approvals.findIndex((a) => a.approvalId === approval.approvalId)
  if (index === -1) return [...approvals, approval]
  const next = [...approvals]
  next[index] = approval
  return next
}

/**
 * Accumulates privacy state for one active chat and exposes it to the overlay
 * (PrivacyPanel, BlockedCounter, RestorationAnnotations, ToolApprovalPrompt).
 *
 * Mounted beside ``ClientProvider`` in ``App.tsx``. When ``chatId`` is null
 * (no active chat) the provider holds the empty state; on chat switch it resets
 * and re-subscribes so two sessions never blend their entities.
 */
export function PrivacyStateProvider({
  client,
  chatId,
  children,
}: {
  client: PrivacyLaneClient | null
  chatId: string | null
  children: ReactNode
}) {
  const [state, setState] = useState<PrivacyStateValue>(EMPTY_STATE)
  const stateRef = useRef(state)
  stateRef.current = state

  const applyEvent = useCallback((event: PrivacyEvent) => {
    setState((current) => {
      let snapshot = current.snapshot
      let turns = current.turns
      const timelinesByTurnId = { ...current.timelinesByTurnId }
      const annotationsByReplyTo = { ...current.annotationsByReplyTo }
      let approvals = current.approvals

      if (event.kind === 'snapshot') {
        snapshot = event.snapshot
      } else if (event.kind === 'trace') {
        turns = mergeTurn(turns, event.turn)
        timelinesByTurnId[event.turn.turnId] = event.timeline
        for (const approval of event.turn.toolApprovals ?? []) {
          approvals = mergeApproval(approvals, approval)
        }
      } else if (event.kind === 'approval') {
        approvals = mergeApproval(approvals, event.approval)
      } else if (event.kind === 'payload') {
        snapshot = event.payload.privacy
        turns = mergeTurn(turns, event.payload.privacyTurn)
        timelinesByTurnId[event.payload.privacyTurn.turnId] = event.payload.privacyTimeline
        for (const approval of event.payload.privacyTurn.toolApprovals ?? []) {
          approvals = mergeApproval(approvals, approval)
        }
        if (event.replyTo) {
          annotationsByReplyTo[event.replyTo] = event.payload.privacyAnnotations
        }
      }

      return {
        snapshot,
        turns,
        timelinesByTurnId,
        annotationsByReplyTo,
        approvals,
        stats: computeStats(snapshot, turns),
      }
    })
  }, [])

  useEffect(() => {
    setState(EMPTY_STATE)
    if (!client || !chatId) return
    return onPrivacy(client, chatId, applyEvent)
  }, [client, chatId, applyEvent])

  const value = useMemo(() => state, [state])
  return <PrivacyStateContext.Provider value={value}>{children}</PrivacyStateContext.Provider>
}

export function usePrivacyState(): PrivacyStateValue {
  return useContext(PrivacyStateContext)
}

/** Restoration annotations for one assistant message id (empty when none). */
export function usePrivacyAnnotations(messageId: string | undefined): PrivacyAnnotation[] {
  const { annotationsByReplyTo } = usePrivacyState()
  if (!messageId) return []
  return annotationsByReplyTo[messageId] ?? []
}
