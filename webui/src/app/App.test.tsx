import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App shell', () => {
  it('renders desktop chat layout with session rail and privacy inspector', () => {
    render(<App />)

    expect(screen.getByRole('complementary', { name: 'Session Rail' })).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: 'Privacy Inspector' }).length).toBeGreaterThan(0)
  })

  it('shows global entries in session rail and keeps chat as default surface', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Skills' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Chat' })).not.toBeInTheDocument()
    expect(screen.getAllByPlaceholderText('Ask Cloakbot anything...').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: 'Settings' }))

    expect(screen.getAllByText('Workspace Profile').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: 'New Chat' }))

    expect(screen.getAllByPlaceholderText('Ask Cloakbot anything...').length).toBeGreaterThan(0)
  })

  it('toggles the desktop sidebar button label', async () => {
    const user = userEvent.setup()
    render(<App />)

    const toggle = screen.getByLabelText('Collapse sidebar')
    await user.click(toggle)

    expect(screen.getByLabelText('Expand sidebar')).toBeInTheDocument()
  })

  it('renders chat composer controls with accessible send action', () => {
    render(<App />)

    expect(screen.getAllByPlaceholderText('Ask Cloakbot anything...').length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Send message' }).length).toBeGreaterThan(0)
  })

  it('renders a global theme switch in the shell header', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getAllByRole('button', { name: 'Theme' })[0]!)

    expect(screen.getByText('Light')).toBeInTheDocument()
    expect(screen.getByText('System')).toBeInTheDocument()
    expect(screen.getByText('Dark')).toBeInTheDocument()
  })
})
