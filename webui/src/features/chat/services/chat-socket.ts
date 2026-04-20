import type { PrivacyTurn } from '@/features/privacy/types'

import type { ChatSessionState, ChatSocketEvent } from '../types'

export const emptyPrivacySnapshot: ChatSessionState['privacySnapshot'] = {
  total_entities: 0,
  entities: [],
  entity_counts: [],
}

function upsertPrivacyTurn(state: ChatSessionState, privacyTurn: PrivacyTurn) {
  const existingIndex = state.privacyTurns.findIndex((turn) => turn.turnId === privacyTurn.turnId)
  if (existingIndex >= 0) {
    const nextTurns = [...state.privacyTurns]
    nextTurns[existingIndex] = privacyTurn
    return nextTurns
  }

  return [...state.privacyTurns, privacyTurn]
}

export function reduceChatSocketEvent(
  state: ChatSessionState,
  event: ChatSocketEvent,
  createMessageId: () => string,
): ChatSessionState {
  if (event.type === 'assistant_message') {
    return {
      messages: [
        ...state.messages,
        {
          id: createMessageId(),
          role: 'assistant',
          content: event.content,
          privacyAnnotations: event.privacyAnnotations ?? [],
        },
      ],
      privacySnapshot: event.privacy ?? state.privacySnapshot,
      privacyTurns: event.privacyTurn ? upsertPrivacyTurn(state, event.privacyTurn) : state.privacyTurns,
    }
  }

  if (event.type === 'assistant_delta') {
    const nextMessages = [...state.messages]
    const lastMessage = nextMessages.at(-1)

    if (lastMessage && lastMessage.role === 'assistant') {
      nextMessages[nextMessages.length - 1] = {
        ...lastMessage,
        content: lastMessage.content + event.content,
      }
    } else {
      nextMessages.push({
        id: createMessageId(),
        role: 'assistant',
        content: event.content,
        privacyAnnotations: [],
      })
    }

    return {
      ...state,
      messages: nextMessages,
    }
  }

  if (event.type === 'assistant_done') {
    const nextMessages = [...state.messages]

    if (event.privacyAnnotations) {
      const lastMessage = nextMessages.at(-1)
      if (lastMessage && lastMessage.role === 'assistant') {
        nextMessages[nextMessages.length - 1] = {
          ...lastMessage,
          privacyAnnotations: event.privacyAnnotations,
        }
      }
    }

    return {
      messages: nextMessages,
      privacySnapshot: event.privacy ?? state.privacySnapshot,
      privacyTurns: event.privacyTurn ? upsertPrivacyTurn(state, event.privacyTurn) : state.privacyTurns,
    }
  }

  if (event.type === 'privacy_snapshot') {
    return {
      ...state,
      privacySnapshot: event.data ?? emptyPrivacySnapshot,
    }
  }

  return state
}
