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
    toolResults: [],
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
          createTurn({ turnId: 'turn-2', intent: 'chat', remotePrompt: 'second sanitized' }),
        ]}
      />,
    )

    expect(screen.getByRole('button', { name: /Turn 1/i })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('button', { name: /Turn 2/i })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByText((content) => content.includes('chat') && content.includes('Sanitized')).length).toBe(2)
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

  it('renders sanitized tool results for each turn', () => {
    render(
      <PromptLog
        turns={[
          createTurn({
            turnId: 'turn-1',
            remotePrompt: 'Please inspect <<PRIVATE_URL_1>>',
            toolResults: [
              {
                toolCallId: 'call-1',
                toolName: 'read_file',
                remoteArguments: { path: '<<PRIVATE_URL_1>>' },
                sanitizedOutput: 'Owner: <<PERSON_1>>',
                wasSanitized: true,
              },
            ],
          }),
        ]}
      />,
    )

    expect(screen.getByText('read_file')).toBeInTheDocument()
    expect(screen.getByText('Output sanitized')).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes('Owner: <<PERSON_1>>'))).toBeInTheDocument()
    expect(screen.getAllByText((content) => content.includes('<<PRIVATE_URL_1>>')).length).toBeGreaterThan(0)
  })

  it('renders visual redaction summaries for tool results', () => {
    render(
      <PromptLog
        turns={[
          createTurn({
            turnId: 'turn-1',
            remotePrompt: 'Please inspect <<PRIVATE_URL_1>>',
            toolResults: [
              {
                toolCallId: 'call-1',
                toolName: 'read_file',
                remoteArguments: { path: '<<PRIVATE_URL_1>>' },
                sanitizedOutput: '[redacted image]',
                wasSanitized: true,
                visualRedactions: [
                  {
                    sourcePath: '/tmp/invoice.png',
                    status: 'redacted',
                    detectedItems: 2,
                    redactionBoxes: 3,
                    labels: ['invoice_number', 'amount'],
                  },
                ],
              },
            ],
          }),
        ]}
      />,
    )

    expect(screen.getByText(/Visual redaction/i)).toBeInTheDocument()
    expect(screen.getByText(/redacted · 2 detected · 3 boxes/i)).toBeInTheDocument()
    expect(screen.getByText(/invoice_number, amount/i)).toBeInTheDocument()
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
