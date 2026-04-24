export type LocalComputation = {
  snippet_index: number
  expression: string
  resolved_expression: string
  result: number
  formatted_result: string
}

export type PrivacyTurn = {
  turnId: string
  intent: 'chat' | 'math' | 'doc'
  remotePrompt: string
  localComputations: LocalComputation[]
}

export type PrivacyTimelineEvent = {
  eventType: string
  sequence: number
  stage: 'raw' | 'sanitized' | 'postprocessed'
  status: 'started' | 'succeeded' | 'failed'
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
  severity: 'high' | 'medium' | 'low'
  canonical: string
  aliases: string[]
  value: string | number | null
  formula?: string | null
}

export type PrivacySummary = {
  entity_type: string
  severity: 'high' | 'medium' | 'low'
  count: number
}

export type PrivacyEntity = {
  placeholder: string
  entity_type: string
  severity: 'high' | 'medium' | 'low'
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
