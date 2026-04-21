import { useCallback, useEffect, useRef, useState } from 'react'

import { ChatView } from '@/features/chat/components/ChatView'
import { useChatSession } from '@/features/chat/hooks/use-chat-session'
import { scrollMessageListToBottom } from '@/features/chat/lib/scroll-message-list'

type NavigationSession = {
  id: string
  title: string
}

type ChatNavigationState = {
  sessions: NavigationSession[]
  activeSessionId: string
  onSelectSession: (id: string) => void
  onStartNewSession: () => void
}

type ChatPageProps = {
  onSessionNavigationChange?: (state: ChatNavigationState) => void
}

export function ChatPage({ onSessionNavigationChange }: ChatPageProps) {
  const {
    sessions,
    activeSessionId,
    startNewSession,
    selectSession,
    messages,
    privacySnapshot,
    privacyTurns,
    input,
    setInput,
    sendMessage,
    isAwaitingAssistant,
  } = useChatSession()
  const [privacyPanelOpen, setPrivacyPanelOpen] = useState(
    () => (typeof window !== 'undefined' ? window.innerWidth >= 1024 : true),
  )
  const scrollRef = useRef<HTMLDivElement>(null)
  const startNewSessionRef = useRef(startNewSession)
  const selectSessionRef = useRef(selectSession)

  useEffect(() => {
    startNewSessionRef.current = startNewSession
  }, [startNewSession])

  useEffect(() => {
    selectSessionRef.current = selectSession
  }, [selectSession])

  const handleStartNewSession = useCallback(() => {
    startNewSessionRef.current()
  }, [])

  const handleSelectSession = useCallback((id: string) => {
    selectSessionRef.current(id)
  }, [])

  useEffect(() => {
    if (!onSessionNavigationChange) {
      return
    }

    onSessionNavigationChange({
      sessions: sessions.map((session) => ({ id: session.id, title: session.title })),
      activeSessionId,
      onSelectSession: handleSelectSession,
      onStartNewSession: handleStartNewSession,
    })
  }, [activeSessionId, handleSelectSession, handleStartNewSession, onSessionNavigationChange, sessions])

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      scrollMessageListToBottom(scrollRef.current)
    })

    return () => {
      window.cancelAnimationFrame(frame)
    }
  }, [activeSessionId, messages])

  return (
    <ChatView
      activeSessionId={activeSessionId}
      messages={messages}
      privacySnapshot={privacySnapshot}
      privacyTurns={privacyTurns}
      input={input}
      setInput={setInput}
      onSend={sendMessage}
      isAwaitingAssistant={isAwaitingAssistant}
      privacyPanelOpen={privacyPanelOpen}
      setPrivacyPanelOpen={setPrivacyPanelOpen}
      scrollRef={scrollRef}
    />
  )
}
