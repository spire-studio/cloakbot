import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { PrivacyTurn } from '@/features/privacy/types'

import { PromptLog } from './PromptLog'

function createTurn(overrides: Partial<PrivacyTurn>): PrivacyTurn {
  return {
    turnId: 'turn-1',
    intent: 'chat',
    remotePrompt: '<<PERSON_1>> says hello',
    localComputations: [],
    ...overrides,
  }
}

describe('PromptLog', () => {
  it('renders empty state when there are no turns', () => {
    render(<PromptLog turns={[]} />)

    expect(screen.getByText(/Sanitized prompts will appear here/i)).toBeInTheDocument()
  })

  it('renders grouped per-turn records and expands newest turn by default', () => {
    render(
      <PromptLog
        turns={[
          createTurn({ turnId: 'turn-1', intent: 'chat', remotePrompt: 'first sanitized' }),
          createTurn({ turnId: 'turn-2', intent: 'doc', remotePrompt: 'second sanitized' }),
        ]}
      />,
    )

    expect(screen.getByRole('button', { name: /Turn 1/i })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: /Turn 2/i })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText((content) => content.includes('chat') && content.includes('Sanitized'))).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes('doc') && content.includes('Sanitized'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Restored' })).not.toBeInTheDocument()
  })

  it('renders only sanitized payloads', () => {
    render(
      <PromptLog
        turns={[
          createTurn({
            turnId: 'turn-1',
            remotePrompt: '<<PERSON_1>> says hello\nfrom Seattle',
          }),
        ]}
      />,
    )

    expect(
      screen.getByText((content) =>
        content.includes('<<PERSON_1>> says hello') && content.includes('from Seattle'),
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Sanitized payload')).toBeInTheDocument()
    expect(screen.queryByText('Restored payload')).not.toBeInTheDocument()
  })

  it('keeps sanitized payload visible when toggling a turn', async () => {
    const user = userEvent.setup()

    render(
      <PromptLog
        turns={[
          createTurn({
            turnId: 'turn-fallback',
            remotePrompt: 'fallback remote payload',
          }),
        ]}
      />,
    )

    await user.click(screen.getByRole('button', { name: /Turn 1/i }))

    expect(screen.getByText('fallback remote payload')).toBeInTheDocument()
    expect(screen.queryByText('Fallback')).not.toBeInTheDocument()
  })
})
