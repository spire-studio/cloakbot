import type {
  PrivacyAnnotation,
  PrivacySnapshot,
  PrivacyTimeline,
  PrivacyTurn,
  ToolApproval,
  UserAttachmentResult,
} from '@/features/privacy/types'

export type ChatAttachment = {
  mimeType: string
  dataUrl: string
  name?: string
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
  privacyAnnotations?: PrivacyAnnotation[]
  assistantStatus?: ChatAssistantStatus
  toolApproval?: ToolApproval
  /** Attachments uploaded with this user message (originals, local-only). */
  attachments?: ChatAttachment[]
  /** Per-attachment redaction results from the privacy pipeline (server-side). */
  attachmentResults?: UserAttachmentResult[]
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
      privacyTimeline?: PrivacyTimeline
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
      type: 'session'
      sessionId: string
    }
  | {
      type: 'status'
      data: Record<string, string | boolean>
    }
  | {
      type: 'progress'
      content: string
      toolHint: boolean
    }
  | {
      type: 'assistant_message'
      content: string
      privacyAnnotations?: PrivacyAnnotation[]
      privacy?: PrivacySnapshot
      privacyTurn?: PrivacyTurn
      privacyTimeline?: PrivacyTimeline
      toolApproval?: ToolApproval
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
      privacyTimeline?: PrivacyTimeline
    }
  | {
      type: 'privacy_snapshot'
      data?: PrivacySnapshot
    }
