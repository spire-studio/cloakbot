import { useEffect, useRef, useState } from 'react'

import { ChatView } from '@/features/chat/components/ChatView'
import { useChatSession } from '@/features/chat/hooks/use-chat-session'

export function ChatPage() {
  const { messages, privacySnapshot, privacyTurns, input, setInput, sendMessage } = useChatSession()
  const [privacyPanelOpen, setPrivacyPanelOpen] = useState(
    () => (typeof window !== 'undefined' ? window.innerWidth >= 1024 : true),
  )
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!scrollRef.current) {
      return
    }

    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  return (
    <ChatView
      messages={messages}
      privacySnapshot={privacySnapshot}
      privacyTurns={privacyTurns}
      input={input}
      setInput={setInput}
      onSend={sendMessage}
      privacyPanelOpen={privacyPanelOpen}
      onTogglePrivacyPanel={() => setPrivacyPanelOpen((previous) => !previous)}
      scrollRef={scrollRef}
    />
  )
}
