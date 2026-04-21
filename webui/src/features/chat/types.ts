import type {
  PrivacyAnnotation,
  PrivacySnapshot,
  PrivacyTurn,
} from '@/features/privacy/types'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
  privacyAnnotations?: PrivacyAnnotation[]
  assistantStatus?: ChatAssistantStatus
}

export type ChatAssistantStatus =
  | {
      state: 'thinking'
      startedAt: number
    }
  | {
      state: 'done'
      startedAt: number
      finishedAt: number
    }

export type ChatSessionState = {
  messages: ChatMessage[]
  privacySnapshot: PrivacySnapshot
  privacyTurns: PrivacyTurn[]
}

export type ChatSessionRecord = {
  id: string
  title: string
  messages: ChatMessage[]
  privacySnapshot: PrivacySnapshot
  privacyTurns: PrivacyTurn[]
  createdAt: number
  updatedAt: number
}

export type ChatSocketEvent =
  | {
      type: 'assistant_message'
      content: string
      privacyAnnotations?: PrivacyAnnotation[]
      privacy?: PrivacySnapshot
      privacyTurn?: PrivacyTurn
    }
  | {
      type: 'assistant_delta'
      content: string
    }
  | {
      type: 'assistant_done'
      privacyAnnotations?: PrivacyAnnotation[]
      privacy?: PrivacySnapshot
      privacyTurn?: PrivacyTurn
    }
  | {
      type: 'privacy_snapshot'
      data?: PrivacySnapshot
    }
