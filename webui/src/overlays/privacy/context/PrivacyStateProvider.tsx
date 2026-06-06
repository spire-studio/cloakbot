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
  type PrivacyPayload,
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
  approvals: ToolApproval[]
  stats: PrivacyHeaderStats
}

const EMPTY_STATE: PrivacyStateValue = {
  snapshot: EMPTY_SNAPSHOT,
  turns: [],
  timelinesByTurnId: {},
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
 * Fold one decoded privacy event into the accumulated state (pure). Shared by
 * the live lane and the refresh-path history rehydration so a replayed payload
 * settles identically to a live one.
 */
function reducePrivacyState(current: PrivacyStateValue, event: PrivacyEvent): PrivacyStateValue {
  let snapshot = current.snapshot
  let turns = current.turns
  const timelinesByTurnId = { ...current.timelinesByTurnId }
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
  }

  return {
    snapshot,
    turns,
    timelinesByTurnId,
    approvals,
    stats: computeStats(snapshot, turns),
  }
}

/**
 * Seed state from the persisted per-turn privacy log (refresh rehydration).
 *
 * A payload whose ``turnId`` is already present is skipped so a live event that
 * landed before the (async) history fetch resolved is never clobbered by its
 * older persisted copy. On a cold refresh ``current`` is empty, so every payload
 * folds in.
 */
function foldPrivacyHistory(current: PrivacyStateValue, payloads: PrivacyPayload[]): PrivacyStateValue {
  let next = current
  for (const payload of payloads) {
    const turnId = payload.privacyTurn?.turnId
    if (turnId && next.turns.some((turn) => turn.turnId === turnId)) continue
    next = reducePrivacyState(next, { kind: 'payload', payload })
  }
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
  loadHistory,
  children,
}: {
  client: PrivacyLaneClient | null
  chatId: string | null
  /** Refresh rehydration: fetch the persisted per-turn privacy log for the
   * active chat. Omitted in tests / non-localhost so the overlay stays
   * live-only and additive. */
  loadHistory?: () => Promise<PrivacyPayload[]>
  children: ReactNode
}) {
  const [state, setState] = useState<PrivacyStateValue>(EMPTY_STATE)
  const stateRef = useRef(state)
  stateRef.current = state

  const applyEvent = useCallback((event: PrivacyEvent) => {
    setState((current) => reducePrivacyState(current, event))
  }, [])

  useEffect(() => {
    setState(EMPTY_STATE)
    if (!client || !chatId) return
    const unsubscribe = onPrivacy(client, chatId, applyEvent)
    if (!loadHistory) return unsubscribe
    // Rehydrate the inspector from disk so a page refresh restores the entity
    // list, remote-prompt turns, and approvals. Live events merge on top; the
    // fold skips turnIds already present so it never clobbers fresher live data.
    let cancelled = false
    void loadHistory()
      .then((payloads) => {
        if (cancelled || !payloads.length) return
        setState((current) => foldPrivacyHistory(current, payloads))
      })
      .catch(() => {
        /* best-effort: the overlay degrades to live-only on fetch failure */
      })
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [client, chatId, applyEvent, loadHistory])

  const value = useMemo(() => state, [state])
  return <PrivacyStateContext.Provider value={value}>{children}</PrivacyStateContext.Provider>
}

export function usePrivacyState(): PrivacyStateValue {
  return useContext(PrivacyStateContext)
}
