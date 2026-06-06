import { describe, expect, it } from 'vitest'

import { buildRemoteView } from '@/overlays/privacy/lib/remote-view'
import type { PrivacyAnnotation } from '@/overlays/privacy/types'

const mk = (over: Partial<PrivacyAnnotation>): PrivacyAnnotation => ({
  annotation_type: 'entity',
  placeholder: '<<X_1>>',
  text: 'x',
  start: 0,
  end: 1,
  entity_type: 'person',
  severity: 'high',
  canonical: 'x',
  aliases: ['x'],
  value: null,
  ...over,
})

describe('buildRemoteView', () => {
  it('swaps a restored span back to its placeholder and re-points the annotation', () => {
    const content = 'Your name is Alice Chen.'
    const anns = [mk({ placeholder: '<<PERSON_1>>', text: 'Alice Chen', start: 13, end: 23, canonical: 'Alice Chen' })]
    const remote = buildRemoteView(content, anns)
    expect(remote.content).toBe('Your name is <<PERSON_1>>.')
    expect(remote.annotations).toHaveLength(1)
    const a = remote.annotations[0]
    expect(remote.content.slice(a.start, a.end)).toBe('<<PERSON_1>>')
    expect(a.canonical).toBe('Alice Chen') // entity metadata preserved for hover
  })

  it('handles multiple spans and preserves the text between them', () => {
    const content = 'Hi Alice Chen, email alice@acme.com.'
    const anns = [
      mk({ placeholder: '<<PERSON_1>>', text: 'Alice Chen', start: 3, end: 13 }),
      mk({ placeholder: '<<EMAIL_1>>', text: 'alice@acme.com', start: 21, end: 35 }),
    ]
    const remote = buildRemoteView(content, anns)
    expect(remote.content).toBe('Hi <<PERSON_1>>, email <<EMAIL_1>>.')
    expect(remote.annotations.map((a) => remote.content.slice(a.start, a.end))).toEqual([
      '<<PERSON_1>>',
      '<<EMAIL_1>>',
    ])
  })

  it('skips out-of-range spans rather than corrupting the text', () => {
    expect(buildRemoteView('abc', [mk({ start: 1, end: 99 })]).content).toBe('abc')
  })

  it('returns content unchanged when there are no annotations', () => {
    expect(buildRemoteView('plain', []).content).toBe('plain')
  })
})
