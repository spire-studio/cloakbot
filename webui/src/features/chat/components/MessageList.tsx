import { Check, ChevronDown, ChevronRight, Copy, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState, type RefObject } from 'react'

import { Button } from '@/components/ui/button'
import { Chip } from '@/components/ui/chip'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { ChatAssistantStatus, ChatMessage } from '@/features/chat/types'
import type { PrivacyTimeline, PrivacyTimelineEvent, ToolApproval } from '@/features/privacy/types'
import { AnnotatedMarkdown } from '@/features/privacy/lib/annotated-markdown'
import { cn } from '@/lib/utils'

type MessageListProps = {
  messages: ChatMessage[]
  scrollRef: RefObject<HTMLDivElement | null>
  onApproveToolCall: (approvalId: string) => void
}

export function MessageList({ messages, scrollRef, onApproveToolCall }: MessageListProps) {
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const copiedResetTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (copiedResetTimeoutRef.current !== null) {
        window.clearTimeout(copiedResetTimeoutRef.current)
      }
    }
  }, [])

  const handleCopy = async (message: ChatMessage) => {
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard) {
        return
      }

      await navigator.clipboard.writeText(message.content)
      setCopiedMessageId(message.id)

      if (copiedResetTimeoutRef.current !== null) {
        window.clearTimeout(copiedResetTimeoutRef.current)
      }

      copiedResetTimeoutRef.current = window.setTimeout(() => {
        setCopiedMessageId((current) => (current === message.id ? null : current))
        copiedResetTimeoutRef.current = null
      }, 1200)
    } catch {
      setCopiedMessageId((current) => (current === message.id ? null : current))
    }
  }

  return (
    <ScrollArea className="min-h-0 h-full flex-1 px-4 py-5 lg:px-5" ref={scrollRef}>
      <div className="mx-auto flex max-w-[52rem] flex-col gap-7 pb-4 pt-1">
        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              'chat-message-enter flex w-full',
              message.role === 'user' ? 'justify-end' : 'justify-start',
            )}
            >
              <div
                className={cn(
                  'group/message flex min-w-0 flex-col',
                  message.role === 'user' ? 'max-w-[38rem] items-end' : 'w-full max-w-[46rem] items-start',
                )}
              >
                {message.role === 'assistant' && message.assistantStatus ? (
                  <AssistantStatusLine assistantStatus={message.assistantStatus} />
                ) : null}

                <div
                  className={cn(
                  'min-w-0 text-[15px] leading-[1.7]',
                  message.role === 'assistant'
                    ? 'chat-assistant-message w-full text-[1.03rem] text-foreground'
                    : 'rounded-[20px] rounded-tr-sm bg-chat-user-bubble px-5 py-3.5 text-card-foreground',
                  message.role === 'assistant' && !message.content ? 'hidden' : '',
                )}
              >
                  {message.role === 'assistant' ? (
                  <AnnotatedMarkdown
                    content={message.content}
                    annotations={message.privacyAnnotations ?? []}
                  />
                ) : (
                  <div className="whitespace-pre-wrap break-words">{message.content}</div>
                )}
              </div>

              {message.role === 'assistant' && message.toolApproval ? (
                <ToolApprovalPanel
                  approval={message.toolApproval}
                  onApprove={onApproveToolCall}
                />
              ) : null}

              <div
                className={cn(
                  'mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground transition-opacity',
                  message.role === 'assistant'
                    ? (message.content ? 'opacity-100' : 'hidden')
                    : 'pointer-events-none opacity-0 group-hover/message:pointer-events-auto group-hover/message:opacity-100 group-focus-within/message:pointer-events-auto group-focus-within/message:opacity-100',
                )}
              >
                <span>{formatMessageTime(message.createdAt)}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 rounded-md px-2 text-[11px] text-muted-foreground hover:text-foreground"
                  onClick={() => handleCopy(message)}
                  aria-label={`Copy ${message.role} message`}
                >
                  {copiedMessageId === message.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  <span>{copiedMessageId === message.id ? 'Copied' : 'Copy'}</span>
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}

function ToolApprovalPanel({
  approval,
  onApprove,
}: {
  approval: ToolApproval
  onApprove: (approvalId: string) => void
}) {
  const isPending = approval.status === 'pending'

  return (
    <div className="mt-3 w-full rounded-lg border border-border bg-card p-3 text-sm shadow-[0_4px_18px_var(--shadow-soft)]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <ShieldCheck className="h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <div className="truncate font-medium text-foreground">
              {approval.toolName}
            </div>
            <div className="text-xs text-muted-foreground">
              {formatPrivacyClass(approval.privacyClass)} tool
            </div>
          </div>
        </div>
        <Chip className={isPending ? 'border-[var(--privacy-medium-border)] bg-[var(--privacy-medium-bg)] text-[var(--privacy-medium-text)]' : 'border-[var(--privacy-low-border)] bg-[var(--privacy-low-bg)] text-[var(--privacy-low-text)]'}>
          {approval.status}
        </Chip>
      </div>

      {approval.detectedEntities.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {approval.detectedEntities.map((entity, index) => (
            <Chip key={`${approval.approvalId}-${entity.entity_type}-${index}`}>
              {formatEventLabel(entity.entity_type)}
            </Chip>
          ))}
        </div>
      ) : null}

      <pre className="mt-3 max-h-36 overflow-auto rounded-md bg-[var(--surface-subtle)] p-2 font-mono text-[11px] leading-5 text-muted-foreground">
        {JSON.stringify(approval.restoredArguments, null, 2)}
      </pre>

      {isPending ? (
        <div className="mt-3 flex justify-end">
          <Button
            type="button"
            size="sm"
            className="h-8 rounded-md px-3"
            onClick={() => onApprove(approval.approvalId)}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>Approve</span>
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function formatPrivacyClass(value: ToolApproval['privacyClass']) {
  return value.replaceAll('_', ' ')
}

function formatMessageTime(timestamp: number) {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(timestamp)
}

function AssistantStatusLine({ assistantStatus }: { assistantStatus: ChatAssistantStatus }) {
  const [timelineOpen, setTimelineOpen] = useState(false)

  if (assistantStatus.state === 'thinking') {
    return (
      <div className="mb-2 flex w-full justify-start" aria-live="polite">
        <div className="text-[15px] leading-[1.7] text-card-foreground">
          <span>Thinking</span>
          <span aria-hidden="true" className="ml-0.5 inline-flex w-[1.5rem] justify-start">
            <span className="chat-thinking-dot">.</span>
            <span className="chat-thinking-dot [animation-delay:0.2s]">.</span>
            <span className="chat-thinking-dot [animation-delay:0.4s]">.</span>
          </span>
          <span className="sr-only">Bot is thinking</span>
        </div>
      </div>
    )
  }

  const statusLabel = `Done in ${formatAssistantDuration(assistantStatus.startedAt, assistantStatus.finishedAt)}`
  const timeline = assistantStatus.privacyTimeline

  if (!timeline || timeline.events.length === 0) {
    return (
      <div className="mb-2 flex w-full justify-start" aria-live="polite">
        <div className="text-[15px] leading-[1.7] text-card-foreground">
          <span>{statusLabel}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="mb-2 w-full" aria-live="polite">
      <button
        type="button"
        className="flex max-w-full items-center gap-2 rounded-md py-1 pl-0 pr-1.5 text-left text-[13px] leading-none text-muted-foreground transition-colors hover:bg-secondary/70 hover:text-foreground focus-visible:bg-secondary/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => setTimelineOpen((current) => !current)}
        aria-expanded={timelineOpen}
      >
        {timelineOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <span className="text-foreground">{statusLabel}</span>
        <Chip>Privacy trace</Chip>
        <Chip>{timeline.events.length} events</Chip>
        <Chip>{formatDurationMs(timeline.totalDurationMs)}</Chip>
      </button>

      {timelineOpen && (
        <div className="mt-2 max-w-full rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground shadow-[0_4px_18px_var(--shadow-soft)]">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <Chip variant="fill">Trace {shortTraceId(timeline.traceId)}</Chip>
            {Object.entries(timeline.stageDurationsMs).map(([stage, duration]) => (
              <Chip key={`${timeline.turnId}-${stage}`}>{formatEventLabel(stage)} {formatDurationMs(duration)}</Chip>
            ))}
          </div>

          <ol className="space-y-1.5">
            {timeline.events.map((event) => (
              <li
                key={`${event.sequence}-${event.eventType}`}
                className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-2 rounded-md border border-border/70 bg-[var(--surface-subtle)] px-2.5 py-2"
              >
                <div className="font-mono text-[11px] text-muted-foreground">#{event.sequence}</div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate font-medium text-foreground">{formatEventLabel(event.eventType)}</span>
                    <Chip className={privacyStatusClasses(event.status)}>{event.status}</Chip>
                    <Chip>{event.stage}</Chip>
                    {event.durationMs !== null && <Chip>{formatDurationMs(event.durationMs)}</Chip>}
                  </div>
                  <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
                    {formatPayloadSummary(event)}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

function privacyStatusClasses(status: PrivacyTimelineEvent['status']) {
  if (status === 'failed') {
    return 'border-[var(--privacy-high-border)] bg-[var(--privacy-high-bg)] text-[var(--privacy-high-text)]'
  }
  if (status === 'succeeded') {
    return 'border-[var(--privacy-low-border)] bg-[var(--privacy-low-bg)] text-[var(--privacy-low-text)]'
  }
  return 'border-[var(--privacy-medium-border)] bg-[var(--privacy-medium-bg)] text-[var(--privacy-medium-text)]'
}

function formatEventLabel(value: string) {
  return value
    .replaceAll('.', ' ')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function formatPayloadSummary(event: PrivacyTimelineEvent) {
  const entries = Object.entries(event.payload)
  if (entries.length === 0) {
    return event.spanId
  }

  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(' | ')
}

function formatDurationMs(durationMs: number) {
  if (durationMs < 1000) {
    return `${durationMs}ms`
  }

  return `${(durationMs / 1000).toFixed(1)}s`
}

function shortTraceId(traceId: PrivacyTimeline['traceId']) {
  if (traceId.length <= 18) {
    return traceId
  }

  return `${traceId.slice(0, 8)}...${traceId.slice(-6)}`
}

function formatAssistantDuration(startedAt: number, finishedAt: number) {
  const durationMs = Math.max(0, finishedAt - startedAt)
  const durationSeconds = Math.max(1, Math.round(durationMs / 1000))
  return `${durationSeconds}s`
}
