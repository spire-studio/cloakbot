import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { useChatSession } from './use-chat-session'

const openReadyState = 1

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('useChatSession', () => {
  it('adds user message, sends payload, and clears input when socket is writable', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1000)
    const send = vi.fn()

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => ({
          send,
          close: vi.fn(),
          readyState: openReadyState,
        }),
      }),
    )

    act(() => {
      result.current.setInput('hello world')
    })
    act(() => {
      result.current.sendMessage()
    })

    expect(result.current.messages.find((message) => message.role === 'user')).toMatchObject({
      role: 'user',
      content: 'hello world',
    })
    expect(result.current.messages.at(-1)).toMatchObject({
      role: 'assistant',
      content: '',
      assistantStatus: {
        state: 'thinking',
        startedAt: 1000,
      },
    })
    expect(send).toHaveBeenCalledWith(JSON.stringify({ content: 'hello world' }))
    expect(result.current.input).toBe('')
    expect(result.current.isAwaitingAssistant).toBe(true)
  })

  it('treats readyState 1 as writable for injected sockets without depending on WebSocket.OPEN', () => {
    vi.stubGlobal('WebSocket', { OPEN: 99 })
    const send = vi.fn()

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => ({
          send,
          close: vi.fn(),
          readyState: openReadyState,
        }),
      }),
    )

    act(() => {
      result.current.setInput('hello again')
    })
    act(() => {
      result.current.sendMessage()
    })

    expect(send).toHaveBeenCalledWith(JSON.stringify({ content: 'hello again' }))
    expect(result.current.messages.findLast((message) => message.role === 'user')).toMatchObject({
      role: 'user',
      content: 'hello again',
    })
    expect(result.current.input).toBe('')
  })

  it('appends the user message even when socket is not writable', () => {
    const send = vi.fn()

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => ({
          send,
          close: vi.fn(),
          readyState: 0,
        }),
      }),
    )

    const beforeCount = result.current.messages.length

    act(() => {
      result.current.setInput('queued')
    })
    act(() => {
      result.current.sendMessage()
    })

    expect(send).not.toHaveBeenCalled()
    expect(result.current.messages).toHaveLength(beforeCount + 1)
    expect(result.current.messages.at(-1)).toMatchObject({
      role: 'user',
      content: 'queued',
    })
    expect(result.current.input).toBe('')
  })

  it('generates distinct default ids across multiple sends once prior turn completes', () => {
    vi.spyOn(Date, 'now').mockReturnValue(123)
    const socket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => socket,
      }),
    )

    act(() => {
      result.current.setInput('first')
    })
    act(() => {
      result.current.sendMessage()
    })

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_done' }),
        } as MessageEvent<string>,
      )
    })

    act(() => {
      result.current.setInput('second')
    })
    act(() => {
      result.current.sendMessage()
    })

    const userMessages = result.current.messages.filter((message) => message.role === 'user')

    expect(userMessages).toHaveLength(2)
    expect(userMessages[0]?.id).not.toBe(userMessages[1]?.id)
  })

  it('keeps the same socket when rerendered with new callback identities', () => {
    const firstSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
    }
    const secondSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
    }
    const createSocketSpy = vi
      .fn<(url: string) => typeof firstSocket>()
      .mockReturnValueOnce(firstSocket)
      .mockReturnValueOnce(secondSocket)

    const { rerender, unmount } = renderHook(
      ({ createSocket, createMessageId }) => useChatSession({ createSocket, createMessageId }),
      {
        initialProps: {
          createSocket: (url: string) => createSocketSpy(url),
          createMessageId: () => 'initial-id',
        },
      },
    )

    expect(createSocketSpy).toHaveBeenCalledTimes(1)

    rerender({
      createSocket: (url: string) => createSocketSpy(url),
      createMessageId: () => 'rerender-id',
    })

    expect(createSocketSpy).toHaveBeenCalledTimes(1)
    expect(firstSocket.close).not.toHaveBeenCalled()
    expect(secondSocket.close).not.toHaveBeenCalled()

    unmount()

    expect(firstSocket.close).toHaveBeenCalledTimes(1)
    expect(secondSocket.close).not.toHaveBeenCalled()
  })

  it('sets session title from first user message only', () => {
    const socket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => socket,
      }),
    )

    act(() => {
      result.current.setInput('   Hello   world   from title   ')
    })
    act(() => {
      result.current.sendMessage()
    })

    const activeSession = result.current.sessions.find(
      (session) => session.id === result.current.activeSessionId,
    )
    expect(activeSession?.title).toBe('Hello world from title')

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_done' }),
        } as MessageEvent<string>,
      )
    })

    act(() => {
      result.current.setInput('second message')
    })
    act(() => {
      result.current.sendMessage()
    })

    const activeSessionAfterSecondMessage = result.current.sessions.find(
      (session) => session.id === result.current.activeSessionId,
    )
    expect(activeSessionAfterSecondMessage?.title).toBe('Hello world from title')
  })

  it('isolates messages when switching sessions', () => {
    const socket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const createSessionId = vi
      .fn<() => string>()
      .mockReturnValueOnce('session-1')
      .mockReturnValueOnce('session-2')

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => socket,
        createSessionId,
      }),
    )

    act(() => {
      result.current.setInput('message in first session')
    })
    act(() => {
      result.current.sendMessage()
    })

    const firstSessionId = result.current.activeSessionId

    act(() => {
      result.current.startNewSession()
    })

    const secondSessionId = result.current.activeSessionId
    expect(secondSessionId).not.toBe(firstSessionId)

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_done' }),
        } as MessageEvent<string>,
      )
    })

    act(() => {
      result.current.setInput('message in second session')
    })
    act(() => {
      result.current.sendMessage()
    })

    const secondSession = result.current.sessions.find((session) => session.id === secondSessionId)
    expect(secondSession?.messages.some((message) => message.content === 'message in second session')).toBe(
      true,
    )

    act(() => {
      result.current.selectSession(firstSessionId)
    })

    expect(
      result.current.messages.some((message) => message.content === 'message in first session'),
    ).toBe(true)
    expect(
      result.current.messages.some((message) => message.content === 'message in second session'),
    ).toBe(false)
  })

  it('blocks second send while assistant response is in flight and keeps input unchanged', () => {
    const socket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => socket,
      }),
    )

    act(() => {
      result.current.setInput('first')
    })
    act(() => {
      result.current.sendMessage()
    })

    expect(result.current.isAwaitingAssistant).toBe(true)

    act(() => {
      result.current.setInput('second blocked')
    })
    act(() => {
      result.current.sendMessage()
    })

    expect(socket.send).toHaveBeenCalledTimes(1)
    expect(result.current.input).toBe('second blocked')

    const userMessages = result.current.messages.filter((message) => message.role === 'user')
    expect(userMessages.map((message) => message.content)).toEqual(['first'])

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_done' }),
        } as MessageEvent<string>,
      )
    })

    expect(result.current.isAwaitingAssistant).toBe(false)
  })

  it('routes assistant events to the pinned origin session even after switching sessions', () => {
    const socket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }
    const createSessionId = vi
      .fn<() => string>()
      .mockReturnValueOnce('session-a')
      .mockReturnValueOnce('session-b')

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => socket,
        createSessionId,
      }),
    )

    const sessionAId = result.current.activeSessionId

    act(() => {
      result.current.setInput('hello from A')
    })
    act(() => {
      result.current.sendMessage()
    })

    act(() => {
      result.current.startNewSession()
    })

    const sessionBId = result.current.activeSessionId
    expect(sessionBId).not.toBe(sessionAId)

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_message', content: 'reply for A' }),
        } as MessageEvent<string>,
      )
    })

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_done' }),
        } as MessageEvent<string>,
      )
    })

    const sessionA = result.current.sessions.find((session) => session.id === sessionAId)
    const sessionB = result.current.sessions.find((session) => session.id === sessionBId)

    expect(
      sessionA?.messages.some(
        (message) => message.role === 'assistant' && message.content === 'reply for A',
      ),
    ).toBe(true)
    expect(sessionB?.messages.some((message) => message.content === 'reply for A')).toBe(false)
  })

  it('ignores malformed socket payloads and continues processing valid events', () => {
    const socket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => socket,
      }),
    )

    const beforeCount = result.current.messages.length

    act(() => {
      socket.onmessage?.({ data: '{invalid-json' } as MessageEvent<string>)
    })

    expect(result.current.messages).toHaveLength(beforeCount)

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_message', content: 'valid event' }),
        } as MessageEvent<string>,
      )
    })

    expect(result.current.messages.at(-1)).toMatchObject({
      role: 'assistant',
      content: 'valid event',
    })
  })

  it('ignores blank input when sending', () => {
    const send = vi.fn()

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => ({
          send,
          close: vi.fn(),
          readyState: openReadyState,
        }),
      }),
    )

    const beforeCount = result.current.messages.length
    act(() => {
      result.current.setInput('   ')
    })
    act(() => {
      result.current.sendMessage()
    })

    expect(result.current.messages).toHaveLength(beforeCount)
    expect(send).not.toHaveBeenCalled()
  })

  it('keeps a done status with elapsed time after assistant_done arrives', () => {
    let now = 1000
    vi.spyOn(Date, 'now').mockImplementation(() => now)

    const socket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: openReadyState,
      onmessage: null as ((event: MessageEvent<string>) => void) | null,
    }

    const { result } = renderHook(() =>
      useChatSession({
        createSocket: () => socket,
      }),
    )

    act(() => {
      result.current.setInput('hello')
    })
    act(() => {
      result.current.sendMessage()
    })

    now = 13000

    act(() => {
      socket.onmessage?.(
        {
          data: JSON.stringify({ type: 'assistant_done' }),
        } as MessageEvent<string>,
      )
    })

    expect(result.current.isAwaitingAssistant).toBe(false)
    expect(result.current.messages.at(-1)).toMatchObject({
      role: 'assistant',
      assistantStatus: {
        state: 'done',
        startedAt: 1000,
        finishedAt: 13000,
      },
    })
  })
})
