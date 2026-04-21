import { describe, expect, it, vi } from 'vitest'

import { scrollMessageListToBottom } from '@/features/chat/lib/scroll-message-list'

describe('scrollMessageListToBottom', () => {
  it('smooth-scrolls the Radix viewport instead of the outer scroll area root', () => {
    const scrollRoot = document.createElement('div')
    const viewport = document.createElement('div')
    const scrollTo = vi.fn()

    viewport.setAttribute('data-radix-scroll-area-viewport', '')
    Object.defineProperty(scrollRoot, 'scrollHeight', { configurable: true, value: 120 })
    Object.defineProperty(viewport, 'scrollHeight', { configurable: true, value: 480 })
    Object.defineProperty(viewport, 'scrollTo', { configurable: true, value: scrollTo })

    scrollRoot.scrollTop = 0
    viewport.scrollTop = 0
    scrollRoot.appendChild(viewport)

    scrollMessageListToBottom(scrollRoot)

    expect(scrollTo).toHaveBeenCalledWith({
      top: 480,
      behavior: 'smooth',
    })
    expect(scrollRoot.scrollTop).toBe(0)
  })
})
