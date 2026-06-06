import { describe, expect, it } from 'vitest'

import { bindPrivacyAnnotations } from '@/overlays/privacy/lib/rehydrate'
import { makeAnnotation, makePayload } from '@/overlays/privacy/lib/__fixtures__'
import type { UIMessage } from '@/lib/types'

// makeAnnotation default: text 'Ada Lovelace', start 6, end 18.
const VALID_CONTENT = 'Hello Ada Lovelace'

function asst(content: string, extra: Partial<UIMessage> = {}): UIMessage {
  return { id: 'm', role: 'assistant', content, createdAt: 0, ...extra }
}

describe('bindPrivacyAnnotations', () => {
  it('binds a turn to the assistant message whose offsets validate', () => {
    const messages = [asst('Hi'), asst(VALID_CONTENT)]
    const out = bindPrivacyAnnotations(messages, [makePayload()])
    expect(out[0].privacyAnnotations).toBeUndefined()
    expect(out[1].privacyAnnotations).toHaveLength(1)
    expect((out[1].privacyAnnotations as { text: string }[])[0].text).toBe('Ada Lovelace')
  })

  it('stamps the matched message with the turn id so the activity row can scope to it', () => {
    const out = bindPrivacyAnnotations([asst(VALID_CONTENT)], [makePayload()])
    expect(out[0].privacyAnnotations).toHaveLength(1)
    expect(out[0].privacyTurnId).toBe('turn-1')
  })

  it('consumes each payload at most once (no double assignment)', () => {
    const messages = [asst(VALID_CONTENT), asst(VALID_CONTENT)]
    const out = bindPrivacyAnnotations(messages, [makePayload()])
    expect(out[0].privacyAnnotations).toHaveLength(1)
    expect(out[1].privacyAnnotations).toBeUndefined()
  })

  it('assigns two turns to two matching messages in order', () => {
    const messages = [asst(VALID_CONTENT), asst(VALID_CONTENT)]
    const out = bindPrivacyAnnotations(messages, [makePayload(), makePayload()])
    expect(out[0].privacyAnnotations).toHaveLength(1)
    expect(out[1].privacyAnnotations).toHaveLength(1)
  })

  it('leaves a message un-highlighted when offsets do not validate', () => {
    // Content shifted by one char: slice(6,18) no longer equals 'Ada Lovelace'.
    const out = bindPrivacyAnnotations([asst('Hello! Ada Lovelace')], [makePayload()])
    expect(out[0].privacyAnnotations).toBeUndefined()
  })

  it('ignores trace and user messages', () => {
    const trace = asst(VALID_CONTENT, { role: 'tool', kind: 'trace' })
    const user = asst(VALID_CONTENT, { role: 'user' })
    const out = bindPrivacyAnnotations([trace, user], [makePayload()])
    expect(out[0].privacyAnnotations).toBeUndefined()
    expect(out[1].privacyAnnotations).toBeUndefined()
  })

  it('does not overwrite messages that already carry annotations', () => {
    const existing = [makeAnnotation({ text: 'kept' })]
    const out = bindPrivacyAnnotations(
      [asst(VALID_CONTENT, { privacyAnnotations: existing })],
      [makePayload()],
    )
    expect(out[0].privacyAnnotations).toBe(existing)
  })

  it('returns the input untouched when no turns carry annotations', () => {
    const messages = [asst(VALID_CONTENT)]
    const out = bindPrivacyAnnotations(messages, [makePayload({ privacyAnnotations: [] })])
    expect(out).toBe(messages)
  })
})
