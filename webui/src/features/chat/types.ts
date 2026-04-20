import type {
  PrivacyAnnotation,
  PrivacySnapshot,
  PrivacyTurn,
} from '@/features/privacy/types'

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  privacyAnnotations?: PrivacyAnnotation[]
}

export type ChatSessionState = {
  messages: ChatMessage[]
  privacySnapshot: PrivacySnapshot
  privacyTurns: PrivacyTurn[]
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
