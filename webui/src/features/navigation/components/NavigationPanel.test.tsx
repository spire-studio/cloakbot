import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { NavigationPanel } from './NavigationPanel'

describe('NavigationPanel', () => {
  it('renders session title button', () => {
    render(
      <NavigationPanel
        sessions={[{ id: 'session-1', title: 'First session title' }]}
        activeSessionId="session-1"
        currentView="chat"
        onSelectGlobalView={vi.fn()}
        onSelectSession={vi.fn()}
        onStartNewSession={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'First session title' })).toBeInTheDocument()
  })

  it('clicking session row triggers callback with id', async () => {
    const user = userEvent.setup()
    const onSelectSession = vi.fn()

    render(
      <NavigationPanel
        sessions={[
          { id: 'session-1', title: 'First session title' },
          { id: 'session-2', title: 'Second session title' },
        ]}
        activeSessionId="session-1"
        currentView="chat"
        onSelectGlobalView={vi.fn()}
        onSelectSession={onSelectSession}
        onStartNewSession={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Second session title' }))

    expect(onSelectSession).toHaveBeenCalledWith('session-2')
  })

  it('new chat button triggers callback', async () => {
    const user = userEvent.setup()
    const onStartNewSession = vi.fn()

    render(
      <NavigationPanel
        sessions={[{ id: 'session-1', title: 'First session title' }]}
        activeSessionId="session-1"
        currentView="chat"
        onSelectGlobalView={vi.fn()}
        onSelectSession={vi.fn()}
        onStartNewSession={onStartNewSession}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'New Chat' }))

    expect(onStartNewSession).toHaveBeenCalledTimes(1)
  })

  it('matches session row sizing with the new chat button', () => {
    render(
      <NavigationPanel
        sessions={[{ id: 'session-1', title: 'First session title' }]}
        activeSessionId="session-1"
        currentView="chat"
        onSelectGlobalView={vi.fn()}
        onSelectSession={vi.fn()}
        onStartNewSession={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'New Chat' })).toHaveClass('h-9', 'rounded-lg')
    expect(screen.getByRole('button', { name: 'First session title' })).toHaveClass('h-8', 'rounded-lg')
  })

  it('keeps horizontal padding for collapsed session rows', () => {
    render(
      <NavigationPanel
        sessions={[{ id: 'session-1', title: 'First session title' }]}
        activeSessionId="session-1"
        currentView="chat"
        onSelectGlobalView={vi.fn()}
        onSelectSession={vi.fn()}
        onStartNewSession={vi.fn()}
        collapsed
      />,
    )

    expect(screen.getByRole('button', { name: 'First session title' })).toHaveClass('px-2', 'text-center')
  })
})
