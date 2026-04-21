import { CircleAlert, LoaderCircle, UserRound } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  streaming?: boolean
}

type MessageBubbleProps = {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'

  return (
    <div className={cn('flex gap-3', isUser && 'justify-end')}>
      {!isUser && (
        <div
          className={cn(
            'mt-1 flex size-9 shrink-0 items-center justify-center rounded-full border',
            isSystem ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary',
          )}
        >
          {isSystem ? (
            <CircleAlert className="size-4" />
          ) : (
            <img src="/cloakbot-logo.svg" alt="Cloakbot logo" className="size-5 object-contain" />
          )}
        </div>
      )}

      <Card
        className={cn(
          'max-w-[85%] rounded-3xl px-4 py-3 shadow-none',
          isUser && 'border-primary/20 bg-primary text-primary-foreground',
          !isUser && !isSystem && 'bg-card',
          isSystem && 'border-destructive/20 bg-destructive/5',
        )}
      >
        <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] opacity-70">
          {isUser ? <UserRound className="size-3.5" /> : null}
          <span>{message.role}</span>
          {message.streaming ? <LoaderCircle className="size-3.5 animate-spin" /> : null}
        </div>
        <p className="whitespace-pre-wrap text-sm leading-7">{message.content || ' '}</p>
      </Card>
    </div>
  )
}
