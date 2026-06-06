import type {
  PrivacyAnnotation,
  PrivacyPayload,
  PrivacySnapshot,
  PrivacyTimeline,
  PrivacyTurn,
  ToolApproval,
} from '@/overlays/privacy/types'

export function makeSnapshot(overrides: Partial<PrivacySnapshot> = {}): PrivacySnapshot {
  return {
    total_entities: 2,
    entities: [
      {
        placeholder: '<<PERSON_1>>',
        entity_type: 'PERSON',
        severity: 'high',
        canonical: 'Ada Lovelace',
        aliases: ['Ada', 'Ada Lovelace'],
        value: null,
        created_turn: 'turn-1',
        last_seen_turn: 'turn-1',
      },
      {
        placeholder: '<<EMAIL_1>>',
        entity_type: 'EMAIL_ADDRESS',
        severity: 'medium',
        canonical: 'ada@example.com',
        aliases: ['ada@example.com'],
        value: null,
        created_turn: 'turn-1',
        last_seen_turn: 'turn-1',
      },
    ],
    entity_counts: [
      { entity_type: 'PERSON', severity: 'high', count: 1 },
      { entity_type: 'EMAIL_ADDRESS', severity: 'medium', count: 1 },
    ],
    ...overrides,
  }
}

export function makeTurn(overrides: Partial<PrivacyTurn> = {}): PrivacyTurn {
  return {
    turnId: 'turn-1',
    intent: 'chat',
    remotePrompt: 'Email <<PERSON_1>> at <<EMAIL_1>> about <<PERSON_1>> plan.',
    localComputations: [],
    toolResults: [],
    toolApprovals: [],
    userAttachments: [],
    userDocuments: [],
    ...overrides,
  }
}

export function makeTimeline(overrides: Partial<PrivacyTimeline> = {}): PrivacyTimeline {
  return {
    turnId: 'turn-1',
    traceId: 'trace-1',
    totalDurationMs: 42,
    stageDurationsMs: { sanitize: 12, restore: 8 },
    events: [],
    ...overrides,
  }
}

export function makeAnnotation(overrides: Partial<PrivacyAnnotation> = {}): PrivacyAnnotation {
  return {
    annotation_type: 'entity',
    placeholder: '<<PERSON_1>>',
    text: 'Ada Lovelace',
    start: 6,
    end: 18,
    entity_type: 'PERSON',
    severity: 'high',
    canonical: 'Ada Lovelace',
    aliases: ['Ada Lovelace'],
    value: null,
    formula: null,
    ...overrides,
  }
}

export function makeApproval(overrides: Partial<ToolApproval> = {}): ToolApproval {
  return {
    approvalId: 'appr-1',
    toolCallId: 'call-1',
    toolName: 'send_email',
    privacyClass: 'external',
    remoteArguments: { to: '<<EMAIL_1>>' },
    restoredArguments: { to: 'ada@example.com' },
    detectedEntities: [{ text: 'ada@example.com', entity_type: 'EMAIL_ADDRESS', severity: 'high' }],
    status: 'pending',
    ...overrides,
  }
}

export function makePayload(overrides: Partial<PrivacyPayload> = {}): PrivacyPayload {
  return {
    privacy: makeSnapshot(),
    privacyAnnotations: [makeAnnotation()],
    privacyTurn: makeTurn(),
    privacyTimeline: makeTimeline(),
    ...overrides,
  }
}
