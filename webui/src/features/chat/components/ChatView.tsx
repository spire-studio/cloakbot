import type { RefObject } from 'react'

import type { ChatMessage } from '@/features/chat/types'
import { PrivacyPanel } from '@/features/privacy/components/PrivacyPanel'
import type { PrivacySnapshot, PrivacyTurn } from '@/features/privacy/types'

import { Composer } from './Composer'
import { MessageList } from './MessageList'

type ChatViewProps = {
  messages: ChatMessage[]
  privacySnapshot: PrivacySnapshot
  privacyTurns: PrivacyTurn[]
  input: string
  setInput: (value: string) => void
  onSend: () => void
  privacyPanelOpen: boolean
  onTogglePrivacyPanel: () => void
  scrollRef: RefObject<HTMLDivElement | null>
}

export function ChatView({
  messages,
  privacySnapshot,
  privacyTurns,
  input,
  setInput,
  onSend,
  privacyPanelOpen,
  onTogglePrivacyPanel,
  scrollRef,
}: ChatViewProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <MessageList messages={messages} scrollRef={scrollRef} />
        <Composer input={input} onInputChange={setInput} onSend={onSend} />
      </div>
      <PrivacyPanel
        open={privacyPanelOpen}
        onToggle={onTogglePrivacyPanel}
        snapshot={privacySnapshot}
        turns={privacyTurns}
      />
    </div>
  )
}
