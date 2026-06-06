/**
 * Refresh-path rehydration helpers for the privacy overlay.
 *
 * The WebUI transcript replays the locally-restored assistant text but carries
 * no restoration annotations — the raw ``agent_ui.privacy`` blob is deliberately
 * never persisted there. On a page refresh the per-message highlights would
 * therefore vanish. The annotations instead live in the gated per-turn privacy
 * log (``GET /api/sessions/{key}/privacy``); this module binds them back onto
 * the replayed messages.
 */
import type { PrivacyAnnotation, PrivacyPayload } from '@/overlays/privacy/types'
import type { UIMessage } from '@/lib/types'

/**
 * Re-attach persisted restoration annotations to replayed assistant messages.
 *
 * Each turn's annotations index that turn's final restored answer string, so we
 * match a payload to the assistant message whose ``content`` validates *every*
 * offset (``content.slice(start, end) === text``). We match by offset rather
 * than message id because replay regenerates ids, and the per-turn log has no
 * stable id to join on. Each payload is consumed at most once; a message whose
 * content fails validation (e.g. a markdown-image rewrite shifted the offsets,
 * or a non-localhost projection redacted the text) is left un-highlighted rather
 * than mis-highlighted. Messages that already carry annotations (live-bound) are
 * left untouched.
 */
export function bindPrivacyAnnotations(
  messages: UIMessage[],
  turns: PrivacyPayload[],
): UIMessage[] {
  const pending = turns
    .map((turn) => ({ anns: turn.privacyAnnotations, turnId: turn.privacyTurn.turnId }))
    .filter(
      (p): p is { anns: PrivacyAnnotation[]; turnId: string } =>
        Array.isArray(p.anns) && p.anns.length > 0,
    )
  if (pending.length === 0) return messages

  const used = new Set<number>()
  return messages.map((message) => {
    if (message.role !== 'assistant' || message.kind === 'trace') return message
    if (message.privacyAnnotations && (message.privacyAnnotations as unknown[]).length > 0) {
      return message
    }
    const content = message.content
    if (typeof content !== 'string' || content.length === 0) return message

    for (let i = 0; i < pending.length; i += 1) {
      if (used.has(i)) continue
      const { anns, turnId } = pending[i]
      const valid = anns.every(
        (a) =>
          a.start >= 0 &&
          a.end <= content.length &&
          a.start <= a.end &&
          content.slice(a.start, a.end) === a.text,
      )
      if (valid) {
        used.add(i)
        return {
          ...message,
          privacyAnnotations: anns,
          ...(turnId ? { privacyTurnId: turnId } : {}),
        }
      }
    }
    return message
  })
}
