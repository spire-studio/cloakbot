import { describe, expect, it } from 'vitest'

import { cn } from './utils'

describe('cn', () => {
  it('returns merged class names', () => {
    expect(cn('px-2', undefined, 'py-1')).toBe('px-2 py-1')
  })
})
