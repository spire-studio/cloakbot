import type { PrivacySnapshot, PrivacyTimeline, PrivacyTurn } from '@/features/privacy/types'

type AuditTurnRecord = {
  kind: 'turn'
  ts: string
  session_id: string
  turn_id: string
  intent: string
  remote_prompt_chars: number
  tool_results: number
  tool_calls: Array<{
    tool_call_id: string
    tool_name: string
    was_sanitized: boolean
    visual_redaction_boxes: number
  }>
  total_duration_ms: number | null
  stage_durations_ms: Record<string, number> | null
}

type AuditEntityRecord = {
  kind: 'entity'
  ts: string
  session_id: string
  placeholder: string
  entity_type: string
  severity: 'high' | 'medium' | 'low'
  created_turn: string | null
  last_seen_turn: string | null
}

export type AuditRecord = AuditTurnRecord | AuditEntityRecord

type BuildAuditOptions = {
  sessionId: string
  snapshot: PrivacySnapshot
  turns: PrivacyTurn[]
  timelinesByTurnId?: Record<string, PrivacyTimeline | undefined>
  now?: Date
}

/**
 * Build an in-memory list of audit rows for export.
 *
 * Schema is intentionally type-and-placeholder only — original values never
 * leave the browser, so the resulting JSONL is safe to attach to a compliance
 * ticket or paste into a shared doc.
 */
export function buildAuditRecords({
  sessionId,
  snapshot,
  turns,
  timelinesByTurnId,
  now = new Date(),
}: BuildAuditOptions): AuditRecord[] {
  const ts = now.toISOString()
  const records: AuditRecord[] = []

  for (const turn of turns) {
    const timeline = timelinesByTurnId?.[turn.turnId]
    records.push({
      kind: 'turn',
      ts,
      session_id: sessionId,
      turn_id: turn.turnId,
      intent: turn.intent,
      remote_prompt_chars: turn.remotePrompt.length,
      tool_results: turn.toolResults?.length ?? 0,
      tool_calls:
        turn.toolResults?.map((result) => ({
          tool_call_id: result.toolCallId,
          tool_name: result.toolName,
          was_sanitized: result.wasSanitized,
          visual_redaction_boxes:
            result.visualRedactions?.reduce((total, item) => total + item.redactionBoxes, 0) ?? 0,
        })) ?? [],
      total_duration_ms: timeline?.totalDurationMs ?? null,
      stage_durations_ms: timeline?.stageDurationsMs ?? null,
    })
  }

  for (const entity of snapshot.entities) {
    records.push({
      kind: 'entity',
      ts,
      session_id: sessionId,
      placeholder: entity.placeholder,
      entity_type: entity.entity_type,
      severity: entity.severity,
      created_turn: entity.created_turn,
      last_seen_turn: entity.last_seen_turn,
    })
  }

  return records
}

export function recordsToJsonl(records: AuditRecord[]): string {
  return records.map((record) => JSON.stringify(record)).join('\n') + (records.length ? '\n' : '')
}

type DownloadOptions = {
  sessionId: string
  filename?: string
}

/**
 * Trigger a JSONL file download in the browser. Safe to call from a click
 * handler; no-op when invoked outside the browser (e.g. tests without DOM).
 */
export function downloadAuditJsonl(records: AuditRecord[], { sessionId, filename }: DownloadOptions) {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return
  }

  const content = recordsToJsonl(records)
  const blob = new Blob([content], { type: 'application/x-ndjson' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download =
    filename ?? `cloakbot-audit-${sessionId.replaceAll(':', '-')}-${formatStamp(new Date())}.jsonl`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

function formatStamp(date: Date): string {
  const pad = (value: number) => value.toString().padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}
