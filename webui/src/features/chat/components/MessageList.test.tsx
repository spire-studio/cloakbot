import { createRef } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '@/features/chat/types'

import { MessageList } from './MessageList'

describe('MessageList', () => {
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
})
