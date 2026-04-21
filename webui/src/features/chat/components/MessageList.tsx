import { Check, Copy } from 'lucide-react'
import { useEffect, useRef, useState, type RefObject } from 'react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { ChatAssistantStatus, ChatMessage } from '@/features/chat/types'
import { AnnotatedMarkdown } from '@/features/privacy/lib/annotated-markdown'
import { cn } from '@/lib/utils'

type MessageListProps = {
  messages: ChatMessage[]
  scrollRef: RefObject<HTMLDivElement | null>
}

export function MessageList({ messages, scrollRef }: MessageListProps) {
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

function formatMessageTime(timestamp: number) {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(timestamp)
}

function AssistantStatusLine({ assistantStatus }: { assistantStatus: ChatAssistantStatus }) {
  const statusLabel =
    assistantStatus.state === 'thinking'
      ? 'Thinking'
      : `Done in ${formatAssistantDuration(assistantStatus.startedAt, assistantStatus.finishedAt)}`

  return (
    <div className="mb-2 flex w-full justify-start" aria-live="polite">
      <div className="text-[15px] leading-[1.7] text-card-foreground">
        <span>{statusLabel}</span>
        {assistantStatus.state === 'thinking' ? (
          <>
            <span aria-hidden="true" className="ml-0.5 inline-flex w-[1.5rem] justify-start">
              <span className="chat-thinking-dot">.</span>
              <span className="chat-thinking-dot [animation-delay:0.2s]">.</span>
              <span className="chat-thinking-dot [animation-delay:0.4s]">.</span>
            </span>
            <span className="sr-only">Bot is thinking</span>
          </>
        ) : null}
      </div>
    </div>
  )
}

function formatAssistantDuration(startedAt: number, finishedAt: number) {
  const durationMs = Math.max(0, finishedAt - startedAt)
  const durationSeconds = Math.max(1, Math.round(durationMs / 1000))
  return `${durationSeconds}s`
}
