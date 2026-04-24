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
  fetchJson?: <T>(url: string) => Promise<T>
}

const defaultInitialMessages: ChatMessage[] = []
const activeSessionStorageKey = 'cloakbot.activeSessionId'

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

function upsertSession(sessions: ChatSessionRecord[], nextSession: ChatSessionRecord) {
  if (sessions.some((session) => session.id === nextSession.id)) {
    return sessions.map((session) => (session.id === nextSession.id ? nextSession : session))
  }
  return [nextSession, ...sessions]
}

function isSocketWritable(socket: SocketLike | null): socket is SocketLike {
  return socket?.readyState === socketOpenReadyState
}

function createSocketUrl(sessionId: string) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat?session_id=${encodeURIComponent(sessionId)}`
}

async function defaultFetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

function readStoredActiveSessionId() {
  if (typeof window === 'undefined') {
    return ''
  }
  return window.localStorage.getItem(activeSessionStorageKey) ?? ''
}

function storeActiveSessionId(sessionId: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(activeSessionStorageKey, sessionId)
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
    fetchJson = defaultFetchJson,
  } = options

  const createSocketRef = useRef(createSocket)
  const createMessageIdRef = useRef(createMessageId)
  const createSessionIdRef = useRef(createSessionId)
  const fetchJsonRef = useRef(fetchJson)
  const initialMessagesRef = useRef(initialMessages)
  const activeSessionIdRef = useRef('')
  const inFlightAssistantSessionIdRef = useRef<string | null>(null)
  const sessionsRef = useRef<ChatSessionRecord[]>([])

  const [bootstrap] = useState(() => {
    const initialSessionId =
      createSessionId === createDefaultSessionId
        ? (readStoredActiveSessionId() || createSessionId())
        : createSessionId()
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
    fetchJsonRef.current = fetchJson
    initialMessagesRef.current = initialMessages
  }, [createSocket, createMessageId, createSessionId, fetchJson, initialMessages])

  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId
  }, [activeSessionId])

  useEffect(() => {
    if (!activeSessionId) {
      return
    }

    const socket = createSocketRef.current(createSocketUrl(activeSessionId))
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
      if (socketRef.current === socket) {
        socketRef.current = null
      }
    }
  }, [activeSessionId])

  useEffect(() => {
    let cancelled = false

    async function loadInitialHistory() {
      try {
        const list = await fetchJsonRef.current<{ sessions: Array<Pick<ChatSessionRecord, 'id' | 'title' | 'createdAt' | 'updatedAt'>> }>('/api/sessions')
        if (cancelled || list.sessions.length === 0) {
          return
        }

        const storedSessionId = readStoredActiveSessionId()
        const selectedSessionId =
          list.sessions.some((session) => session.id === storedSessionId)
            ? storedSessionId
            : list.sessions[0]?.id

        setSessions((previousSessions) => {
          const existingById = new Map(previousSessions.map((session) => [session.id, session]))
          return list.sessions.map((session) => ({
            ...(existingById.get(session.id) ?? createSessionRecord(session.id, [])),
            ...session,
          }))
        })

        if (selectedSessionId) {
          setActiveSessionId(selectedSessionId)
          storeActiveSessionId(selectedSessionId)
          await loadSessionHistory(selectedSessionId, cancelled)
        }
      } catch {
        return
      }
    }

    async function loadSessionHistory(sessionId: string, isCancelled: boolean) {
      try {
        const session = await fetchJsonRef.current<ChatSessionRecord>(`/api/sessions/${encodeURIComponent(sessionId)}`)
        if (isCancelled || cancelled) {
          return
        }
        setSessions((previousSessions) => upsertSession(previousSessions, session))
      } catch {
        return
      }
    }

    void loadInitialHistory()

    return () => {
      cancelled = true
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
    storeActiveSessionId(sessionId)
    setInput('')
  }

  const selectSession = (sessionId: string) => {
    setActiveSessionId(sessionId)
    storeActiveSessionId(sessionId)
    void fetchJsonRef.current<ChatSessionRecord>(`/api/sessions/${encodeURIComponent(sessionId)}`)
      .then((session) => {
        setSessions((previousSessions) => upsertSession(previousSessions, session))
      })
      .catch(() => {})
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
