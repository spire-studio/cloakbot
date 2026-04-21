import { describe, expect, it } from 'vitest'

import { buildSessionTitle } from './session-title'

describe('buildSessionTitle', () => {
  it('returns New chat for blank input', () => {
    expect(buildSessionTitle('   \n\t  ')).toBe('New chat')
  })

  it('returns non-empty non-truncated input as-is', () => {
    const input = 'Hello world'

    expect(buildSessionTitle(input)).toBe(input)
  })

  it('normalizes internal whitespace', () => {
    const input = '  hello\n\t   there   friend  '

    expect(buildSessionTitle(input)).toBe('hello there friend')
  })

  it('does not truncate exactly 48 characters', () => {
    const input = 'a'.repeat(48)

    expect(buildSessionTitle(input)).toBe(input)
    expect(buildSessionTitle(input)).toHaveLength(48)
  })

  it('truncates 49 characters to 47 chars plus ellipsis', () => {
    const input = 'a'.repeat(49)

    expect(buildSessionTitle(input)).toBe(`${'a'.repeat(47)}…`)
    expect(buildSessionTitle(input)).toHaveLength(48)
  })

  it('truncates normalized content to 47 chars plus ellipsis', () => {
    const input = '   ' + 'a'.repeat(60) + '   '

    expect(buildSessionTitle(input)).toBe(`${'a'.repeat(47)}…`)
    expect(buildSessionTitle(input)).toHaveLength(48)
  })
})
