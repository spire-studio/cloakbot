/**
 * Wire types for the CloakBot privacy overlay.
 *
 * These mirror the backend contracts in ``cloakbot/privacy/webui/contracts.py``
 * (the ``by_alias`` JSON shape) plus the side-channel frames built in
 * ``cloakbot/privacy/webui/side_channel.py``. The overlay is the only
 * CloakBot-authored frontend; everything here is consumed off the privacy
 * side-channel (``agent_ui.privacy`` on ``message`` frames + the standalone
 * ``privacy_snapshot`` / ``privacy_trace`` / ``tool_approval`` event frames).
 *
 * Privacy note: a non-localhost client receives a redacted projection (the
 * backend strips ``value`` / ``canonical`` / ``aliases`` / ``originalDataUrl``
 * / ``originalText`` / ``restoredArguments`` and replaces them with a sentinel
 * or ``null``). These types therefore treat every raw-bearing field as
 * nullable so the same components render both projections.
 */

export type Severity = 'high' | 'medium' | 'low'

export type LocalComputation = {
  snippet_index: number
  expression: string
  resolved_expression: string
  result: number
  formatted_result: string
}

export type VisualPrivacyRedaction = {
  sourcePath: string | null
  status: string
  detectedItems: number
  redactionBoxes: number
  labels: string[]
  reason?: string | null
}

export type ToolPrivacyResult = {
  toolCallId: string
  toolName: string
  remoteArguments: Record<string, unknown>
  sanitizedOutput: string
  wasSanitized: boolean
  visualRedactions?: VisualPrivacyRedaction[]
}

export type UserAttachmentResult = {
  status: 'redacted' | 'omitted'
  originalDataUrl?: string | null
  redactedDataUrl?: string | null
  redaction?: VisualPrivacyRedaction | null
  reason?: string | null
}

/**
 * One text-document upload after chunked PII redaction. Sibling of
 * ``UserAttachmentResult`` (which is image-side). ``originalText`` is what
 * the user uploaded (localhost only); ``sanitizedText`` is what the LLM saw.
 */
export type UserDocumentResult = {
  documentName?: string | null
  mimeType: string
  originalSha256: string
  charCount: number
  originalText?: string | null
  sanitizedText: string
  sanitizedPreview: string
  chunksTotal: number
  chunksFailed: boolean
  wasSanitized: boolean
  entityTypes: string[]
}

export type DetectedEntity = {
  text: string
  entity_type: string
  severity?: Severity
  value?: string | number
}

export type ToolApprovalStatus = 'pending' | 'approved' | 'denied'

export type ToolApproval = {
  approvalId: string
  toolCallId: string
  toolName: string
  privacyClass: 'local' | 'external' | 'side_effect'
  remoteArguments: Record<string, unknown>
  restoredArguments: Record<string, unknown>
  detectedEntities: DetectedEntity[]
  status: ToolApprovalStatus
}

export type PrivacyTurn = {
  turnId: string
  intent: 'chat' | 'math'
  remotePrompt: string
  localComputations: LocalComputation[]
  toolResults?: ToolPrivacyResult[]
  toolApprovals?: ToolApproval[]
  userAttachments?: UserAttachmentResult[]
  userDocuments?: UserDocumentResult[]
}

export type PrivacyTimelineEvent = {
  eventType: string
  sequence: number
  stage: string
  status: string
  spanId: string
  parentSpanId: string | null
  timestamp: string
  durationMs: number | null
  payload: Record<string, unknown>
}

export type PrivacyTimeline = {
  turnId: string
  traceId: string
  totalDurationMs: number
  stageDurationsMs: Record<string, number>
  events: PrivacyTimelineEvent[]
}

export type PrivacyAnnotation = {
  annotation_type?: 'entity' | 'local_computation'
  placeholder: string
  text: string
  start: number
  end: number
  entity_type: string
  severity: Severity
  canonical: string
  aliases: string[]
  value: string | number | null
  formula?: string | null
}

export type PrivacySummary = {
  entity_type: string
  severity: Severity
  count: number
}

export type PrivacyEntity = {
  placeholder: string
  entity_type: string
  severity: Severity
  canonical: string
  aliases: string[]
  value: string | number | null
  created_turn: string | null
  last_seen_turn: string | null
}

export type PrivacySnapshot = {
  total_entities: number
  entities: PrivacyEntity[]
  entity_counts: PrivacySummary[]
}

/** The full ``agent_ui.privacy`` blob folded onto ``message``/``assistant_done``. */
export type PrivacyPayload = {
  privacy: PrivacySnapshot
  privacyAnnotations: PrivacyAnnotation[]
  privacyTurn: PrivacyTurn
  privacyTimeline: PrivacyTimeline
}

/** Standalone ``privacy_snapshot`` event frame. */
export type PrivacySnapshotFrame = {
  event: 'privacy_snapshot'
  data: PrivacySnapshot
}

/** Standalone ``privacy_trace`` event frame. */
export type PrivacyTraceFrame = {
  event: 'privacy_trace'
  turn: PrivacyTurn
  timeline: PrivacyTimeline
}

/** Standalone ``tool_approval`` event frame. */
export type ToolApprovalFrame = {
  event: 'tool_approval'
  approval: ToolApproval
}

export const EMPTY_SNAPSHOT: PrivacySnapshot = {
  total_entities: 0,
  entities: [],
  entity_counts: [],
}
