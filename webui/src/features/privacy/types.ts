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
