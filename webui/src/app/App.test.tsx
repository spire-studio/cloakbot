import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App shell', () => {
  it('renders navigation and Cloakbot branding', () => {
    render(<App />)

    expect(screen.getAllByText('Cloakbot').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Chat' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Configuration' })).toBeInTheDocument()
    expect(screen.getAllByAltText('Cloakbot logo').length).toBeGreaterThan(0)
  })

  it('switches to the configuration tab', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Configuration' }))

    expect(screen.getAllByText('Workspace Profile').length).toBeGreaterThan(0)
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
})
