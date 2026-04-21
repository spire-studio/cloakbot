import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Composer } from './Composer'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Composer', () => {
  it('uses a two-line textarea on the landing layout', () => {
    mockTextareaMetrics()

    render(
      <Composer
        input=""
        onInputChange={() => {}}
        onSend={() => {}}
        isAwaitingAssistant={false}
        layout="landing"
      />,
    )

    const textarea = screen.getByPlaceholderText('Ask Cloakbot anything...') as HTMLTextAreaElement

    expect(textarea.rows).toBe(2)
    expect(Number.parseFloat(textarea.style.height)).toBeCloseTo(63.92, 2)
  })

  it('uses a one-line textarea on the conversation layout', () => {
    mockTextareaMetrics()

    render(
      <Composer
        input=""
        onInputChange={() => {}}
        onSend={() => {}}
        isAwaitingAssistant={false}
        layout="conversation"
      />,
    )

    const textarea = screen.getByPlaceholderText('Ask Cloakbot anything...') as HTMLTextAreaElement

    expect(textarea.rows).toBe(1)
    expect(Number.parseFloat(textarea.style.height)).toBeCloseTo(56, 2)
  })
})

function mockTextareaMetrics() {
  vi.spyOn(window, 'getComputedStyle').mockImplementation(
    ((element: Element) => {
      const style = getBaseStyle()
      if (element instanceof HTMLTextAreaElement) {
        return {
          ...style,
          lineHeight: '24px',
          paddingTop: '16px',
          paddingBottom: '16px',
        }
      }

      return style
    }) as typeof window.getComputedStyle,
  )

  Object.defineProperty(HTMLTextAreaElement.prototype, 'scrollHeight', {
    configurable: true,
    get() {
      return 24
    },
  })
}

function getBaseStyle() {
  return {
    getPropertyValue: () => '',
  } as unknown as CSSStyleDeclaration
}
