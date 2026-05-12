import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

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

    render(<MessageList messages={messages} scrollRef={createRef<HTMLDivElement>()} onApproveToolCall={() => {}} />)

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

    render(<MessageList messages={messages} scrollRef={createRef<HTMLDivElement>()} onApproveToolCall={() => {}} />)

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

    render(<MessageList messages={messages} scrollRef={createRef<HTMLDivElement>()} onApproveToolCall={() => {}} />)

    const toggle = screen.getByRole('button', { name: /Done in 12s/i })
    expect(toggle).toHaveTextContent('Privacy trace')

    fireEvent.click(toggle)

    expect(screen.getByText('Turn Sanitize Succeeded')).toBeInTheDocument()
    expect(screen.getByText('was_sanitized: true')).toBeInTheDocument()
  })

  it('renders a pending tool approval action', () => {
    const onApproveToolCall = vi.fn()
    const messages: ChatMessage[] = [
      {
        id: 'assistant-approval',
        role: 'assistant',
        content: 'Tool approval required',
        createdAt: 2,
        toolApproval: {
          approvalId: 'approval-1',
          toolCallId: 'call-1',
          toolName: 'web_search',
          privacyClass: 'external',
          remoteArguments: { query: 'hello <<PERSON_1>>' },
          restoredArguments: { query: 'hello Alice' },
          detectedEntities: [{ text: 'Alice', entity_type: 'person', severity: 'high' }],
          status: 'pending',
        },
      },
    ]

    render(
      <MessageList
        messages={messages}
        scrollRef={createRef<HTMLDivElement>()}
        onApproveToolCall={onApproveToolCall}
      />,
    )

    expect(screen.getByText('web_search')).toBeInTheDocument()
    expect(screen.getByText('external tool')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Approve/i }))

    expect(onApproveToolCall).toHaveBeenCalledWith('approval-1')
  })
})
