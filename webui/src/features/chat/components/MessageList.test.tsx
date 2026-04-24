import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '@/features/chat/types'
import type { PrivacyTimeline } from '@/features/privacy/types'

import { MessageList } from './MessageList'

describe('MessageList', () => {
  const timeline: PrivacyTimeline = {
    turnId: 'turn-1',
    traceId: 'webui:test:turn-1',
    totalDurationMs: 64,
    stageDurationsMs: { sanitize: 12, restore: 8 },
    events: [
      {
        eventType: 'turn.sanitize.succeeded',
        sequence: 1,
        stage: 'sanitized',
        status: 'succeeded',
        spanId: 'turn-1:sanitize:completed',
        parentSpanId: 'turn-1:sanitize',
        timestamp: '2026-04-24T00:00:00Z',
        durationMs: 12,
        payload: { was_sanitized: true },
      },
    ],
  }

  it('renders a thinking indicator above the assistant message it belongs to', () => {
    const messages: ChatMessage[] = [
      {
        id: 'user-1',
        role: 'user',
        content: 'Hello',
        createdAt: 1,
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        content: '',
        createdAt: 2,
        assistantStatus: { state: 'thinking', startedAt: 1000 },
      },
    ]

    render(<MessageList messages={messages} scrollRef={createRef<HTMLDivElement>()} />)

    expect(screen.getByText('Thinking')).toBeInTheDocument()
    expect(screen.getByText('Bot is thinking')).toBeInTheDocument()
    expect(screen.queryByText('Hello', { selector: '.chat-assistant-message *' })).not.toBeInTheDocument()
  })

  it('renders a done status above the assistant content', () => {
    const messages: ChatMessage[] = [
      {
        id: 'user-1',
        role: 'user',
        content: 'Hello',
        createdAt: 1,
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Hi',
        createdAt: 2,
        assistantStatus: { state: 'done', startedAt: 1000, finishedAt: 13000 },
      },
    ]

    render(<MessageList messages={messages} scrollRef={createRef<HTMLDivElement>()} />)

    expect(screen.getByText('Done in 12s')).toBeInTheDocument()
    expect(screen.getByText('Done in 12s').compareDocumentPosition(screen.getByText('Hi'))).toBeTruthy()
  })

  it('expands a completed privacy trace from the assistant status line', () => {
    const messages: ChatMessage[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Hi',
        createdAt: 2,
        assistantStatus: {
          state: 'done',
          startedAt: 1000,
          finishedAt: 13000,
          privacyTimeline: timeline,
        },
      },
    ]

    render(<MessageList messages={messages} scrollRef={createRef<HTMLDivElement>()} />)

    const toggle = screen.getByRole('button', { name: /Done in 12s/i })
    expect(toggle).toHaveTextContent('Privacy trace')

    fireEvent.click(toggle)

    expect(screen.getByText('Turn Sanitize Succeeded')).toBeInTheDocument()
    expect(screen.getByText('was_sanitized: true')).toBeInTheDocument()
  })
})
