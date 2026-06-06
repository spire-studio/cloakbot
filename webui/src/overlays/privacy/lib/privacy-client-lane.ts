/**
 * Privacy client lane — the overlay's read side of the CloakBot side-channel.
 *
 * The backend (Cap F, ``cloakbot/privacy/webui/side_channel.py``) emits privacy
 * data two ways on the SAME socket:
 *
 *   1. folded under ``agent_ui.privacy`` on ``message`` / ``assistant_done``
 *      frames (upstream's ``agent_ui`` passthrough forwards it verbatim), and
 *   2. as standalone ``privacy_snapshot`` / ``privacy_trace`` / ``tool_approval``
 *      event frames.
 *
 * This module is pure frame-classification logic so it can be unit-tested
 * without a WebSocket. ``onPrivacy(client, chatId, handler)`` subscribes the
 * overlay to a chat and decodes every privacy-bearing frame into a
 * :type:`PrivacyEvent`. Upstream frames that carry no privacy data are ignored
 * (the overlay is strictly additive — it never swallows a thread frame).
 *
 * Privacy boundary: this lane only READS what the backend chose to send. The
 * localhost gate already ran server-side, so a non-localhost browser simply
 * receives the redacted projection here — there is no raw value to leak.
 */
import type {
  PrivacyPayload,
  PrivacySnapshot,
  PrivacyTimeline,
  PrivacyTurn,
  ToolApproval,
} from '@/overlays/privacy/types'

/** Decoded privacy event handed to the overlay. */
export type PrivacyEvent =
  | { kind: 'payload'; payload: PrivacyPayload; replyTo?: string }
  | { kind: 'snapshot'; snapshot: PrivacySnapshot }
  | { kind: 'trace'; turn: PrivacyTurn; timeline: PrivacyTimeline }
  | { kind: 'approval'; approval: ToolApproval }

export type PrivacyEventHandler = (event: PrivacyEvent) => void

/** Minimal slice of ``NanobotClient`` the lane depends on (eases testing). */
export interface PrivacyLaneClient {
  onChat(chatId: string, handler: (ev: unknown) => void): () => void
}

type AgentUiBlob = { kind?: string; data?: unknown; privacy?: unknown } | null | undefined

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * Extract a :type:`PrivacyPayload` from a ``message``-frame ``agent_ui`` blob.
 *
 * The backend writes the gated payload to ``agent_ui.privacy``. We accept both
 * the nested form (``{ privacy: {...} }``) and a bare payload (defensive: a
 * future channel might fold it directly). Returns ``null`` when no privacy blob
 * is present, so non-privacy ``agent_ui`` frames pass through untouched.
 */
export function extractPrivacyPayload(agentUi: AgentUiBlob): PrivacyPayload | null {
  if (!isRecord(agentUi)) return null
  const raw = 'privacy' in agentUi ? agentUi.privacy : null
  const candidate = isRecord(raw) ? raw : null
  if (!candidate) return null
  // A valid payload always carries the four privacy keys; guard so a malformed
  // blob doesn't crash the overlay mid-render.
  if (
    !('privacy' in candidate) ||
    !('privacyTurn' in candidate) ||
    !('privacyAnnotations' in candidate) ||
    !('privacyTimeline' in candidate)
  ) {
    return null
  }
  return candidate as unknown as PrivacyPayload
}

/**
 * Classify one inbound WS frame into a :type:`PrivacyEvent`, or ``null`` if the
 * frame carries no privacy data (an ordinary thread/activity frame).
 */
export function classifyPrivacyFrame(ev: unknown): PrivacyEvent | null {
  if (!isRecord(ev)) return null
  const event = ev.event

  if (event === 'privacy_snapshot' && isRecord(ev.data)) {
    return { kind: 'snapshot', snapshot: ev.data as unknown as PrivacySnapshot }
  }

  if (event === 'privacy_trace' && isRecord(ev.turn) && isRecord(ev.timeline)) {
    return {
      kind: 'trace',
      turn: ev.turn as unknown as PrivacyTurn,
      timeline: ev.timeline as unknown as PrivacyTimeline,
    }
  }

  if (event === 'tool_approval' && isRecord(ev.approval)) {
    return { kind: 'approval', approval: ev.approval as unknown as ToolApproval }
  }

  if (event === 'message') {
    const payload = extractPrivacyPayload(ev.agent_ui as AgentUiBlob)
    if (payload) {
      const replyTo = typeof ev.reply_to === 'string' ? ev.reply_to : undefined
      return { kind: 'payload', payload, replyTo }
    }
  }

  return null
}

/**
 * Subscribe *handler* to every privacy-bearing frame for *chatId*.
 *
 * Returns an unsubscribe function. The lane piggybacks on the client's existing
 * ``onChat`` fan-out, so it shares the single multiplexed socket and needs no
 * new transport. Non-privacy frames are silently skipped here; the thread/
 * activity renderers still receive them through their own ``onChat``
 * subscription.
 */
export function onPrivacy(
  client: PrivacyLaneClient,
  chatId: string,
  handler: PrivacyEventHandler,
): () => void {
  return client.onChat(chatId, (ev) => {
    const decoded = classifyPrivacyFrame(ev)
    if (decoded) handler(decoded)
  })
}
