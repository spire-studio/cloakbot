import { describe, expect, it, vi } from 'vitest'

import {
  classifyPrivacyFrame,
  extractPrivacyPayload,
  onPrivacy,
  type PrivacyEvent,
  type PrivacyLaneClient,
} from '@/overlays/privacy/lib/privacy-client-lane'
import { makePayload, makeSnapshot, makeApproval, makeTurn, makeTimeline } from '@/overlays/privacy/lib/__fixtures__'

describe('extractPrivacyPayload', () => {
  it('reads a full payload from a nested agent_ui.privacy blob', () => {
    const payload = makePayload()
    const result = extractPrivacyPayload({ kind: 'privacy', privacy: payload })
    expect(result).not.toBeNull()
    expect(result?.privacy.total_entities).toBe(2)
  })

  it('returns null for a non-privacy agent_ui blob', () => {
    expect(extractPrivacyPayload({ kind: 'tool_progress', data: { foo: 1 } })).toBeNull()
  })

  it('returns null for a malformed privacy blob missing required keys', () => {
    expect(extractPrivacyPayload({ privacy: { privacy: makeSnapshot() } })).toBeNull()
  })

  it('returns null for undefined / non-object input', () => {
    expect(extractPrivacyPayload(undefined)).toBeNull()
    expect(extractPrivacyPayload(null)).toBeNull()
  })
})

describe('classifyPrivacyFrame', () => {
  it('decodes a standalone privacy_snapshot frame', () => {
    const frame = { event: 'privacy_snapshot', chat_id: 'c1', data: makeSnapshot() }
    const decoded = classifyPrivacyFrame(frame)
    expect(decoded?.kind).toBe('snapshot')
    if (decoded?.kind === 'snapshot') expect(decoded.snapshot.total_entities).toBe(2)
  })

  it('decodes a standalone privacy_trace frame', () => {
    const frame = { event: 'privacy_trace', chat_id: 'c1', turn: makeTurn(), timeline: makeTimeline() }
    const decoded = classifyPrivacyFrame(frame)
    expect(decoded?.kind).toBe('trace')
    if (decoded?.kind === 'trace') expect(decoded.turn.turnId).toBe('turn-1')
  })

  it('decodes a standalone tool_approval frame', () => {
    const frame = { event: 'tool_approval', chat_id: 'c1', approval: makeApproval() }
    const decoded = classifyPrivacyFrame(frame)
    expect(decoded?.kind).toBe('approval')
    if (decoded?.kind === 'approval') expect(decoded.approval.approvalId).toBe('appr-1')
  })

  it('decodes a message frame carrying agent_ui.privacy and its reply_to', () => {
    const frame = {
      event: 'message',
      chat_id: 'c1',
      text: 'hi',
      reply_to: 'msg-9',
      agent_ui: { kind: 'privacy', privacy: makePayload() },
    }
    const decoded = classifyPrivacyFrame(frame)
    expect(decoded?.kind).toBe('payload')
    if (decoded?.kind === 'payload') {
      expect(decoded.replyTo).toBe('msg-9')
      expect(decoded.payload.privacyAnnotations).toHaveLength(1)
    }
  })

  it('ignores an ordinary message frame with no privacy blob (additive)', () => {
    expect(classifyPrivacyFrame({ event: 'message', chat_id: 'c1', text: 'hello' })).toBeNull()
  })

  it('ignores unrelated thread frames (delta, turn_end, ready)', () => {
    expect(classifyPrivacyFrame({ event: 'delta', chat_id: 'c1', text: 'x' })).toBeNull()
    expect(classifyPrivacyFrame({ event: 'turn_end', chat_id: 'c1' })).toBeNull()
    expect(classifyPrivacyFrame({ event: 'ready', chat_id: 'c1' })).toBeNull()
  })
})

describe('onPrivacy', () => {
  function fakeClient(): PrivacyLaneClient & { emit: (ev: unknown) => void } {
    let sink: ((ev: unknown) => void) | null = null
    return {
      onChat(_chatId, handler) {
        sink = handler
        return () => {
          sink = null
        }
      },
      emit(ev) {
        sink?.(ev)
      },
    }
  }

  it('forwards only decoded privacy frames to the handler', () => {
    const client = fakeClient()
    const events: PrivacyEvent[] = []
    const unsub = onPrivacy(client, 'c1', (e) => events.push(e))

    client.emit({ event: 'delta', chat_id: 'c1', text: 'noise' })
    client.emit({ event: 'privacy_snapshot', chat_id: 'c1', data: makeSnapshot() })
    client.emit({ event: 'tool_approval', chat_id: 'c1', approval: makeApproval() })

    expect(events.map((e) => e.kind)).toEqual(['snapshot', 'approval'])
    unsub()
    client.emit({ event: 'privacy_snapshot', chat_id: 'c1', data: makeSnapshot() })
    expect(events).toHaveLength(2)
  })

  it('subscribes via the client onChat fan-out (shares one socket)', () => {
    const onChat = vi.fn(() => () => {})
    const client: PrivacyLaneClient = { onChat }
    onPrivacy(client, 'chat-x', () => {})
    expect(onChat).toHaveBeenCalledWith('chat-x', expect.any(Function))
  })
})
