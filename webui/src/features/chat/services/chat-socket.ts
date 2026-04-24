import type { PrivacyTimeline, PrivacyTurn } from '@/features/privacy/types'

import type { ChatAssistantStatus, ChatMessage, ChatSessionState, ChatSocketEvent } from '../types'

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

function startAssistantStatus(startedAt: number): ChatAssistantStatus {
  return {
    state: 'thinking',
    startedAt,
  }
}

function completeAssistantStatus(
  previousStatus: ChatAssistantStatus | undefined,
  finishedAt: number,
  privacyTimeline?: PrivacyTimeline,
): ChatAssistantStatus {
  const startedAt = previousStatus?.startedAt ?? finishedAt

  const nextStatus: ChatAssistantStatus = {
    state: 'done',
    startedAt,
    finishedAt,
  }

  if (privacyTimeline) {
    nextStatus.privacyTimeline = privacyTimeline
  }

  return nextStatus
}

function createAssistantMessage(createMessageId: () => string, content: string, createdAt: number): ChatMessage {
  return {
    id: createMessageId(),
    role: 'assistant',
    content,
    createdAt,
    privacyAnnotations: [],
    assistantStatus: startAssistantStatus(createdAt),
  }
}

function findPendingAssistantIndex(messages: ChatMessage[]) {
  return messages.findLastIndex(
    (message) => message.role === 'assistant' && message.assistantStatus?.state === 'thinking',
  )
}

export function reduceChatSocketEvent(
  state: ChatSessionState,
  event: ChatSocketEvent,
  createMessageId: () => string,
): ChatSessionState {
  if (event.type === 'assistant_message') {
    const nextMessages = [...state.messages]
    const pendingAssistantIndex = findPendingAssistantIndex(nextMessages)

    if (pendingAssistantIndex >= 0) {
      const pendingMessage = nextMessages[pendingAssistantIndex]
      nextMessages[pendingAssistantIndex] = {
        ...pendingMessage,
        content: event.content,
        privacyAnnotations: event.privacyAnnotations ?? pendingMessage.privacyAnnotations ?? [],
      }
    } else {
      nextMessages.push(createAssistantMessage(createMessageId, event.content, Date.now()))
    }

    return {
      messages: nextMessages,
      privacySnapshot: event.privacy ?? state.privacySnapshot,
      privacyTurns: event.privacyTurn ? upsertPrivacyTurn(state, event.privacyTurn) : state.privacyTurns,
    }
  }

  if (event.type === 'assistant_delta') {
    const nextMessages = [...state.messages]
    const pendingAssistantIndex = findPendingAssistantIndex(nextMessages)

    if (pendingAssistantIndex >= 0) {
      const pendingMessage = nextMessages[pendingAssistantIndex]
      nextMessages[pendingAssistantIndex] = {
        ...pendingMessage,
        content: pendingMessage.content + event.content,
      }
    } else {
      nextMessages.push(createAssistantMessage(createMessageId, event.content, Date.now()))
    }

    return {
      ...state,
      messages: nextMessages,
    }
  }

  if (event.type === 'assistant_done') {
    const nextMessages = [...state.messages]
    const pendingAssistantIndex = findPendingAssistantIndex(nextMessages)

    if (pendingAssistantIndex >= 0) {
      const pendingMessage = nextMessages[pendingAssistantIndex]
      nextMessages[pendingAssistantIndex] = {
        ...pendingMessage,
        privacyAnnotations: event.privacyAnnotations ?? pendingMessage.privacyAnnotations,
        assistantStatus: completeAssistantStatus(
          pendingMessage.assistantStatus,
          Date.now(),
          event.privacyTimeline,
        ),
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
