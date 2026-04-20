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

    expect(result.current.messages.at(-1)).toMatchObject({
      role: 'user',
      content: 'hello world',
    })
    expect(send).toHaveBeenCalledWith(JSON.stringify({ content: 'hello world' }))
    expect(result.current.input).toBe('')
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
    expect(result.current.messages.at(-1)).toMatchObject({
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

  it('generates distinct default ids for rapid consecutive user messages', () => {
    vi.spyOn(Date, 'now').mockReturnValue(123)
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
      result.current.setInput('first')
    })
    act(() => {
      result.current.sendMessage()
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
})
