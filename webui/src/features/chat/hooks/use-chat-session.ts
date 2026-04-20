import { useEffect, useRef, useState } from 'react'

import type { ChatMessage, ChatSessionState, ChatSocketEvent } from '../types'
import { emptyPrivacySnapshot, reduceChatSocketEvent } from '../services/chat-socket'

type SocketLike = {
  readyState: number
  send: (payload: string) => void
  close: () => void
  onmessage?: ((event: MessageEvent<string>) => void) | null
}

const socketOpenReadyState = 1
let messageIdCounter = 0

type UseChatSessionOptions = {
  createSocket?: (url: string) => SocketLike
  createMessageId?: () => string
  initialMessages?: ChatMessage[]
}

const defaultInitialMessages: ChatMessage[] = [
  {
    id: '1',
    role: 'assistant',
    content: 'Hello! I am Cloakbot. How can I assist you today?',
  },
]

function createDefaultSocket(url: string): SocketLike {
  return new WebSocket(url)
}

function createDefaultMessageId() {
  messageIdCounter = (messageIdCounter + 1) % Number.MAX_SAFE_INTEGER
  return `${Date.now()}-${messageIdCounter}`
}

function isSocketWritable(socket: SocketLike | null): socket is SocketLike {
  return socket?.readyState === socketOpenReadyState
}

function createSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

export function useChatSession(options: UseChatSessionOptions = {}) {
  const {
    createSocket = createDefaultSocket,
    createMessageId = createDefaultMessageId,
    initialMessages = defaultInitialMessages,
  } = options

  const [state, setState] = useState<ChatSessionState>({
    messages: initialMessages,
    privacySnapshot: emptyPrivacySnapshot,
    privacyTurns: [],
  })
  const [input, setInput] = useState('')
  const socketRef = useRef<SocketLike | null>(null)
  const createSocketRef = useRef(createSocket)
  const createMessageIdRef = useRef(createMessageId)

  useEffect(() => {
    createSocketRef.current = createSocket
    createMessageIdRef.current = createMessageId
  }, [createSocket, createMessageId])

  useEffect(() => {
    const socket = createSocketRef.current(createSocketUrl())
    socketRef.current = socket

    socket.onmessage = (event) => {
      const parsed = JSON.parse(event.data) as ChatSocketEvent
      setState((previousState) =>
        reduceChatSocketEvent(previousState, parsed, () => createMessageIdRef.current()),
      )
    }

    return () => {
      socket.close()
      socketRef.current = null
    }
  }, [])

  const sendMessage = () => {
    const trimmed = input.trim()
    if (!trimmed) {
      return
    }

    const nextMessage = {
      id: createMessageIdRef.current(),
      role: 'user' as const,
      content: trimmed,
    }

    setState((previousState) => ({
      ...previousState,
      messages: [...previousState.messages, nextMessage],
    }))

    const socket = socketRef.current
    if (isSocketWritable(socket)) {
      socket.send(JSON.stringify({ content: trimmed }))
    }

    setInput('')
  }

  return {
    messages: state.messages,
    privacySnapshot: state.privacySnapshot,
    privacyTurns: state.privacyTurns,
    input,
    setInput,
    sendMessage,
  }
}
