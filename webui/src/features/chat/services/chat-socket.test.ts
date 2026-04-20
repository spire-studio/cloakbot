import { describe, expect, it } from 'vitest'

import type { PrivacySnapshot, PrivacyTurn } from '@/features/privacy/types'

import type { ChatSessionState } from '../types'

import {
  emptyPrivacySnapshot,
  reduceChatSocketEvent,
} from './chat-socket'

function createState(overrides: Partial<ChatSessionState> = {}): ChatSessionState {
  return {
    messages: [],
    privacySnapshot: emptyPrivacySnapshot,
    privacyTurns: [],
    ...overrides,
  }
}

describe('reduceChatSocketEvent', () => {
  it('appends assistant_message and applies privacy payloads', () => {
    const nextSnapshot: PrivacySnapshot = {
      total_entities: 1,
      entities: [
        {
          placeholder: '<<PERSON_1>>',
          entity_type: 'person_name',
          severity: 'high',
          canonical: 'Alice',
          aliases: ['Alice'],
          value: 'Alice',
          created_turn: 'turn-1',
          last_seen_turn: 'turn-1',
        },
      ],
      entity_counts: [{ entity_type: 'person_name', severity: 'high', count: 1 }],
    }

    const nextTurn: PrivacyTurn = {
      turnId: 'turn-1',
      intent: 'chat',
      remotePrompt: 'hello <<PERSON_1>>',
      localComputations: [],
    }

    const result = reduceChatSocketEvent(
      createState(),
      {
        type: 'assistant_message',
        content: 'Hello there',
        privacy: nextSnapshot,
        privacyTurn: nextTurn,
      },
      () => 'assistant-1',
    )

    expect(result.messages).toEqual([
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Hello there',
        privacyAnnotations: [],
      },
    ])
    expect(result.privacySnapshot).toEqual(nextSnapshot)
    expect(result.privacyTurns).toEqual([nextTurn])
  })

  it('extends existing assistant content when receiving assistant_delta', () => {
    const result = reduceChatSocketEvent(
      createState({
        messages: [{ id: 'a1', role: 'assistant', content: 'Hello', privacyAnnotations: [] }],
      }),
      {
        type: 'assistant_delta',
        content: ' world',
      },
      () => 'unused-id',
    )

    expect(result.messages).toEqual([
      {
        id: 'a1',
        role: 'assistant',
        content: 'Hello world',
        privacyAnnotations: [],
      },
    ])
  })

  it('creates assistant message for assistant_delta when last message is not assistant', () => {
    const result = reduceChatSocketEvent(
      createState({
        messages: [{ id: 'u1', role: 'user', content: 'ping' }],
      }),
      {
        type: 'assistant_delta',
        content: 'pong',
      },
      () => 'assistant-2',
    )

    expect(result.messages).toEqual([
      { id: 'u1', role: 'user', content: 'ping' },
      {
        id: 'assistant-2',
        role: 'assistant',
        content: 'pong',
        privacyAnnotations: [],
      },
    ])
  })

  it('applies assistant_done annotations to the latest assistant message', () => {
    const nextTurn: PrivacyTurn = {
      turnId: 'turn-2',
      intent: 'math',
      remotePrompt: 'compute <<NUMBER_1>>+1',
      localComputations: [],
    }

    const result = reduceChatSocketEvent(
      createState({
        messages: [{ id: 'a1', role: 'assistant', content: 'Done', privacyAnnotations: [] }],
      }),
      {
        type: 'assistant_done',
        privacyAnnotations: [
          {
            placeholder: '<<NUMBER_1>>',
            text: '12',
            start: 0,
            end: 2,
            entity_type: 'number',
            severity: 'low',
            canonical: '12',
            aliases: ['12'],
            value: 12,
          },
        ],
        privacyTurn: nextTurn,
      },
      () => 'unused-id',
    )

    expect(result.messages[0]?.privacyAnnotations).toHaveLength(1)
    expect(result.privacyTurns).toEqual([nextTurn])
  })

  it('replaces snapshot on privacy_snapshot events and falls back to empty snapshot', () => {
    const withSnapshot = reduceChatSocketEvent(
      createState(),
      {
        type: 'privacy_snapshot',
        data: {
          total_entities: 2,
          entities: [],
          entity_counts: [],
        },
      },
      () => 'unused-id',
    )

    expect(withSnapshot.privacySnapshot.total_entities).toBe(2)

    const withFallback = reduceChatSocketEvent(
      createState({
        privacySnapshot: withSnapshot.privacySnapshot,
      }),
      {
        type: 'privacy_snapshot',
      },
      () => 'unused-id',
    )

    expect(withFallback.privacySnapshot).toEqual(emptyPrivacySnapshot)
  })
})
