import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import type { ChatMessage } from '@/features/chat/types'
import { PrivacyPanel } from '@/features/privacy/components/PrivacyPanel'
import type { PrivacySnapshot, PrivacyTurn } from '@/features/privacy/types'

import { Composer } from './Composer'
import { MessageList } from './MessageList'

type ChatViewProps = {
  activeSessionId: string
  messages: ChatMessage[]
  privacySnapshot: PrivacySnapshot
  privacyTurns: PrivacyTurn[]
  input: string
  setInput: (value: string) => void
  onSend: () => void
  isAwaitingAssistant: boolean
  privacyPanelOpen: boolean
  setPrivacyPanelOpen: (value: boolean | ((previous: boolean) => boolean)) => void
  scrollRef: RefObject<HTMLDivElement | null>
}

export function ChatView({
  activeSessionId,
  messages,
  privacySnapshot,
  privacyTurns,
  input,
  setInput,
  onSend,
  isAwaitingAssistant,
  privacyPanelOpen,
  setPrivacyPanelOpen,
  scrollRef,
}: ChatViewProps) {
  const [emptyComposerOffset, setEmptyComposerOffset] = useState(0)
  const emptyStateRef = useRef<HTMLDivElement | null>(null)
  const emptyGreeting = useMemo(() => getEmptyGreeting(activeSessionId), [activeSessionId])
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return true
    }

    return window.matchMedia('(min-width: 768px)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }

    const mediaQuery = window.matchMedia('(min-width: 768px)')
    const updateDesktopState = () => {
      setIsDesktop(mediaQuery.matches)
    }

    updateDesktopState()
    mediaQuery.addEventListener('change', updateDesktopState)

    return () => {
      mediaQuery.removeEventListener('change', updateDesktopState)
    }
  }, [])

  useEffect(() => {
    if (messages.length !== 0) {
      return
    }

    const updateEmptyComposerOffset = () => {
      const element = emptyStateRef.current
      if (!element) {
        return
      }

      const rect = element.getBoundingClientRect()
      setEmptyComposerOffset(Math.max(0, window.innerHeight * 0.4 - rect.top))
    }

    updateEmptyComposerOffset()
    window.addEventListener('resize', updateEmptyComposerOffset)

    return () => {
      window.removeEventListener('resize', updateEmptyComposerOffset)
    }
  }, [messages.length])

  return (
    <div className="flex min-h-0 h-full flex-1 overflow-hidden bg-transparent md:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-end border-b border-border px-4 py-2.5 lg:hidden">
          <Button type="button" variant="outline" className="h-8 rounded-lg px-3" onClick={() => setPrivacyPanelOpen(true)}>
            Privacy Inspector
          </Button>
        </div>
        {messages.length === 0 ? (
          <div ref={emptyStateRef} className="flex min-h-0 flex-1 overflow-y-auto px-4 py-8 lg:px-5">
            <div className="relative mx-auto min-h-full w-full max-w-[52rem]">
              <div className="absolute left-1/2 w-full -translate-x-1/2" style={{ top: `${emptyComposerOffset}px` }}>
                <div className="absolute bottom-full left-1/2 mb-8 w-full max-w-[42rem] -translate-x-1/2 text-center">
                  <p className="text-[12px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Cloakbot</p>
                  <h1 className="mt-4 text-balance font-serif text-[2rem] leading-[1.15] text-foreground md:text-[2.65rem]">
                    {emptyGreeting}
                  </h1>
                  <p className="mt-4 text-[15px] leading-[1.8] text-muted-foreground">
                    Cloakbot quietly protects your privacy, every message. ✨
                  </p>
                </div>
                <div className="w-full">
                  <Composer
                    input={input}
                    onInputChange={setInput}
                    onSend={onSend}
                    isAwaitingAssistant={isAwaitingAssistant}
                    layout="landing"
                    className="w-full"
                  />
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <MessageList messages={messages} scrollRef={scrollRef} />
            <Composer
              input={input}
              onInputChange={setInput}
              onSend={onSend}
              isAwaitingAssistant={isAwaitingAssistant}
              layout="conversation"
            />
          </div>
        )}
      </div>

      <div className="hidden md:flex md:shrink-0">
        <h2 className="sr-only">Privacy Inspector</h2>
        <PrivacyPanel
          open={privacyPanelOpen}
          onToggle={() => setPrivacyPanelOpen((previous) => !previous)}
          snapshot={privacySnapshot}
          turns={privacyTurns}
        />
      </div>

      <Sheet open={!isDesktop && privacyPanelOpen} onOpenChange={setPrivacyPanelOpen}>
        <SheetContent side="right" className="w-[min(96vw,420px)] border-l border-border bg-card p-0 sm:max-w-none md:hidden">
          <div className="h-full [&>aside]:h-full [&>aside]:max-h-none [&>aside]:w-full [&>aside]:border-t-0 [&>aside]:bg-background/95">
            <PrivacyPanel
              open
              onToggle={() => setPrivacyPanelOpen(false)}
              snapshot={privacySnapshot}
              turns={privacyTurns}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}

const EMPTY_CHAT_GREETINGS = [
  'Hi! Ready to help whenever you are.',
  'Hey! Great to see you. 👋 ',
  'Hi there! I\'m Cloakbot.',
  'Welcome back! 🙌',
  'Hi! Feel free to ask me anything.',
  'Hey, glad you\'re here! 👋 ',
  'Hello! I\'m all ears (well, text).',
]

const emptyGreetingBySession = new Map<string, string>()

function pickGreeting() {
  return EMPTY_CHAT_GREETINGS[Math.floor(Math.random() * EMPTY_CHAT_GREETINGS.length)]
}

function getEmptyGreeting(sessionId: string) {
  const cachedGreeting = emptyGreetingBySession.get(sessionId)
  if (cachedGreeting) {
    return cachedGreeting
  }

  const nextGreeting = pickGreeting()
  emptyGreetingBySession.set(sessionId, nextGreeting)
  return nextGreeting
}
