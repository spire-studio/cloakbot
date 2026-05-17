import type {
  PrivacyAnnotation,
  PrivacySnapshot,
  PrivacyTimeline,
  PrivacyTurn,
  ToolApproval,
  UserAttachmentResult,
  UserDocumentResult,
} from '@/features/privacy/types'

/**
 * One file the user attached to a message. `kind` discriminates between
 * the image privacy pipeline (OCR + bbox redaction on the visual side)
 * and the document privacy pipeline (chunked text redaction). Older
 * payloads without an explicit `kind` are treated as images for
 * backward compatibility with the first round of upload support.
 */
export type ChatAttachment = {
  mimeType: string
  dataUrl: string
  name?: string
  kind?: 'image' | 'document'
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
  /** Per-image-attachment redaction results from the privacy pipeline (server-side). */
  attachmentResults?: UserAttachmentResult[]
  /** Per-document-upload redaction results from the chunked privacy pipeline. */
  documentResults?: UserDocumentResult[]
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
