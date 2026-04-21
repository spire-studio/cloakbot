import { useEffect, useRef, useState } from 'react'

import { buildSessionTitle } from '@/features/chat/lib/session-title'

import type {
  ChatMessage,
  ChatSessionRecord,
  ChatSessionState,
  ChatSocketEvent,
} from '../types'
import { emptyPrivacySnapshot, reduceChatSocketEvent } from '../services/chat-socket'

type SocketLike = {
  readyState: number
  send: (payload: string) => void
  close: () => void
  onmessage?: ((event: MessageEvent<string>) => void) | null
}

const socketOpenReadyState = 1
let messageIdCounter = 0
let sessionIdCounter = 0

type UseChatSessionOptions = {
  createSocket?: (url: string) => SocketLike
  createMessageId?: () => string
  createSessionId?: () => string
  initialMessages?: ChatMessage[]
}

const defaultInitialMessages: ChatMessage[] = []

function createDefaultSocket(url: string): SocketLike {
  return new WebSocket(url)
}

function createDefaultMessageId() {
  messageIdCounter = (messageIdCounter + 1) % Number.MAX_SAFE_INTEGER
  return `${Date.now()}-${messageIdCounter}`
}

function createDefaultSessionId() {
  sessionIdCounter = (sessionIdCounter + 1) % Number.MAX_SAFE_INTEGER
  return `session-${Date.now()}-${sessionIdCounter}`
}

function createSessionState(initialMessages: ChatMessage[]): ChatSessionState {
  return {
    messages: initialMessages,
    privacySnapshot: emptyPrivacySnapshot,
    privacyTurns: [],
  }
}

function createSessionRecord(id: string, initialMessages: ChatMessage[]): ChatSessionRecord {
  const timestamp = Date.now()

  return {
    id,
    title: 'New chat',
    ...createSessionState(initialMessages),
    createdAt: timestamp,
    updatedAt: timestamp,
  }
}

function isSocketWritable(socket: SocketLike | null): socket is SocketLike {
  return socket?.readyState === socketOpenReadyState
}

function createSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

function createPendingAssistantMessage(createMessageId: () => string, startedAt: number): ChatMessage {
  return {
    id: createMessageId(),
    role: 'assistant',
    content: '',
    createdAt: startedAt,
    privacyAnnotations: [],
    assistantStatus: {
      state: 'thinking',
      startedAt,
    },
  }
}

export function useChatSession(options: UseChatSessionOptions = {}) {
  const {
    createSocket = createDefaultSocket,
    createMessageId = createDefaultMessageId,
    createSessionId = createDefaultSessionId,
    initialMessages = defaultInitialMessages,
  } = options

  const createSocketRef = useRef(createSocket)
  const createMessageIdRef = useRef(createMessageId)
  const createSessionIdRef = useRef(createSessionId)
  const initialMessagesRef = useRef(initialMessages)
  const activeSessionIdRef = useRef('')
  const inFlightAssistantSessionIdRef = useRef<string | null>(null)
  const sessionsRef = useRef<ChatSessionRecord[]>([])

  const [bootstrap] = useState(() => {
    const initialSessionId = createSessionId()
    const initialSession = createSessionRecord(initialSessionId, initialMessages)
    return {
      sessions: [initialSession],
      activeSessionId: initialSessionId,
    }
  })

  const [sessions, setSessions] = useState<ChatSessionRecord[]>(bootstrap.sessions)
  const [activeSessionId, setActiveSessionId] = useState<string>(bootstrap.activeSessionId)
  const [input, setInput] = useState('')
  const [isAwaitingAssistant, setIsAwaitingAssistant] = useState(false)
  const socketRef = useRef<SocketLike | null>(null)

  useEffect(() => {
    createSocketRef.current = createSocket
    createMessageIdRef.current = createMessageId
    createSessionIdRef.current = createSessionId
    initialMessagesRef.current = initialMessages
  }, [createSocket, createMessageId, createSessionId, initialMessages])

  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId
  }, [activeSessionId])

  useEffect(() => {
    const socket = createSocketRef.current(createSocketUrl())
    socketRef.current = socket

    socket.onmessage = (event) => {
      let parsed: ChatSocketEvent
      try {
        parsed = JSON.parse(event.data) as ChatSocketEvent
      } catch {
        return
      }

      const fallbackSessionId = activeSessionIdRef.current || sessionsRef.current[0]?.id || ''
      const pinnedInFlightSessionId = inFlightAssistantSessionIdRef.current
      const targetSessionId =
        parsed.type === 'assistant_message' ||
        parsed.type === 'assistant_delta' ||
        parsed.type === 'assistant_done'
          ? (pinnedInFlightSessionId ?? fallbackSessionId)
          : fallbackSessionId

      if (!targetSessionId) {
        return
      }

      if (
        (parsed.type === 'assistant_message' || parsed.type === 'assistant_delta') &&
        inFlightAssistantSessionIdRef.current === null
      ) {
        inFlightAssistantSessionIdRef.current = targetSessionId
        setIsAwaitingAssistant(true)
      }

      setSessions((previousSessions) =>
        previousSessions.map((session) => {
          if (session.id !== targetSessionId) {
            return session
          }

          const nextState = reduceChatSocketEvent(session, parsed, () => createMessageIdRef.current())

          return {
            ...session,
            ...nextState,
            updatedAt: Date.now(),
          }
        }),
      )

      if (parsed.type === 'assistant_done') {
        inFlightAssistantSessionIdRef.current = null
        setIsAwaitingAssistant(false)
      }
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

    if (inFlightAssistantSessionIdRef.current !== null) {
      return
    }

    const targetSessionId = activeSessionId ?? sessions[0]?.id
    if (!targetSessionId) {
      return
    }

    const nextMessage = {
      id: createMessageIdRef.current(),
      role: 'user' as const,
      content: trimmed,
      createdAt: Date.now(),
    }

    setSessions((previousSessions) =>
      previousSessions.map((session) => {
        if (session.id !== targetSessionId) {
          return session
        }

        const nextMessages = [...session.messages, nextMessage]
        const userMessageCount = nextMessages.filter((message) => message.role === 'user').length

        return {
          ...session,
          messages: nextMessages,
          title: userMessageCount === 1 ? buildSessionTitle(trimmed) : session.title,
          updatedAt: Date.now(),
        }
      }),
    )

    const socket = socketRef.current
    if (isSocketWritable(socket)) {
      try {
        const startedAt = Date.now()
        socket.send(JSON.stringify({ content: trimmed }))
        inFlightAssistantSessionIdRef.current = targetSessionId
        setSessions((previousSessions) =>
          previousSessions.map((session) => {
            if (session.id !== targetSessionId) {
              return session
            }

            return {
              ...session,
              messages: [...session.messages, createPendingAssistantMessage(() => createMessageIdRef.current(), startedAt)],
              updatedAt: Date.now(),
            }
          }),
        )
        setIsAwaitingAssistant(true)
      } catch {
        inFlightAssistantSessionIdRef.current = null
        setIsAwaitingAssistant(false)
      }
    }

    setInput('')
  }

  const startNewSession = () => {
    const sessionId = createSessionIdRef.current()
    const nextSession = createSessionRecord(sessionId, initialMessagesRef.current)

    setSessions((previousSessions) => [nextSession, ...previousSessions])
    setActiveSessionId(sessionId)
    setInput('')
  }

  const selectSession = (sessionId: string) => {
    setActiveSessionId(sessionId)
  }

  const activeSession = sessions.find((session) => session.id === activeSessionId) ?? sessions[0]

  return {
    sessions,
    activeSessionId,
    startNewSession,
    selectSession,
    messages: activeSession?.messages ?? [],
    privacySnapshot: activeSession?.privacySnapshot ?? emptyPrivacySnapshot,
    privacyTurns: activeSession?.privacyTurns ?? [],
    input,
    setInput,
    sendMessage,
    isAwaitingAssistant,
  }
}
