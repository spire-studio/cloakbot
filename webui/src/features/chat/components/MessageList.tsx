import { Sparkles, User } from 'lucide-react'
import type { RefObject } from 'react'

import { Avatar } from '@/components/ui/avatar'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { ChatMessage } from '@/features/chat/types'
import { AnnotatedMarkdown } from '@/features/privacy/lib/annotated-markdown'
import { cn } from '@/lib/utils'
import { BRAND_LOGO_PATH, BRAND_NAME } from '@/shared/constants/brand'

type MessageListProps = {
  messages: ChatMessage[]
  scrollRef: RefObject<HTMLDivElement | null>
}

export function MessageList({ messages, scrollRef }: MessageListProps) {
  return (
    <ScrollArea className="min-h-0 flex-1 px-4 py-6 lg:px-6" ref={scrollRef}>
      <div className="mx-auto flex max-w-4xl flex-col gap-8 pb-4">
        {messages.length === 0 && (
          <div className="flex h-[50vh] flex-col items-center justify-center gap-4 text-muted-foreground opacity-50">
            <Sparkles className="h-12 w-12" />
            <p>Start a conversation with {BRAND_NAME}.</p>
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              'chat-message-enter flex w-full gap-4',
              message.role === 'user' ? 'flex-row-reverse' : '',
            )}
          >
            <Avatar className="mt-0.5 h-8 w-8 shrink-0 ring-1 ring-border/20 shadow-sm">
              {message.role === 'assistant' ? (
                <div className="flex h-full w-full items-center justify-center rounded-full bg-primary/10 p-1">
                  <img src={BRAND_LOGO_PATH} alt="Cloakbot logo" className="h-full w-full object-contain" />
                </div>
              ) : (
                <div className="flex h-full w-full items-center justify-center rounded-full bg-secondary">
                  <User className="h-4 w-4 text-secondary-foreground" />
                </div>
              )}
            </Avatar>

            <div
              className={cn(
                'flex min-w-0 max-w-[85%] flex-col space-y-2',
                message.role === 'user' ? 'items-end' : 'items-start',
              )}
            >
              <div className="flex items-center gap-2 px-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {message.role === 'assistant' ? BRAND_NAME : 'You'}
                </span>
              </div>
              <div
                className={cn(
                  'text-[15px] leading-relaxed',
                  message.role === 'assistant'
                    ? 'rounded-2xl rounded-tl-none border border-border bg-card px-5 py-4 text-card-foreground shadow-sm'
                    : 'rounded-2xl rounded-tr-none bg-primary px-5 py-3 text-primary-foreground shadow-sm',
                )}
              >
                <AnnotatedMarkdown
                  content={message.content}
                  annotations={message.privacyAnnotations ?? []}
                  invert={message.role === 'user'}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
