import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { BlockedCounter } from '@/overlays/privacy/components/BlockedCounter'
import { EntitySummary } from '@/overlays/privacy/components/EntitySummary'
import { ToolApprovalPrompt } from '@/overlays/privacy/components/ToolApprovalPrompt'
import { REDACTED_SENTINEL } from '@/overlays/privacy/lib/severity'
import { makeApproval, makeSnapshot } from '@/overlays/privacy/lib/__fixtures__'

describe('BlockedCounter', () => {
  it('renders nothing at zero', () => {
    const { container } = render(<BlockedCounter total={0} />)
    expect(container.querySelector('[role="status"]')).toBeNull()
  })

  it('renders the count when positive', () => {
    render(<BlockedCounter total={7} />)
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveAttribute(
      'aria-label',
      '7 private values blocked in this session',
    )
  })
})

describe('EntitySummary', () => {
  it('renders canonical values for a localhost (full) snapshot', () => {
    render(<EntitySummary snapshot={makeSnapshot()} />)
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('ada@example.com')).toBeInTheDocument()
  })

  it('masks the canonical when the backend redacted it (non-localhost projection)', () => {
    const redacted = makeSnapshot({
      entities: [
        {
          placeholder: '<<PERSON_1>>',
          entity_type: 'PERSON',
          severity: 'high',
          canonical: REDACTED_SENTINEL,
          aliases: [],
          value: null,
          created_turn: 'turn-1',
          last_seen_turn: 'turn-1',
        },
      ],
      entity_counts: [{ entity_type: 'PERSON', severity: 'high', count: 1 }],
      total_entities: 1,
    })
    render(<EntitySummary snapshot={redacted} />)
    // The raw sentinel string must never be rendered to the user; the row shows
    // a masked placeholder instead, and the placeholder token is still visible.
    expect(screen.queryByText(REDACTED_SENTINEL)).toBeNull()
    expect(screen.getByText('<<PERSON_1>>')).toBeInTheDocument()
    expect(screen.getByText('••••••')).toBeInTheDocument()
  })
})

describe('ToolApprovalPrompt', () => {
  it('shows remote (placeholdered) args but not restored cleartext, and resolves', () => {
    const onResolve = vi.fn()
    render(<ToolApprovalPrompt approval={makeApproval()} onResolve={onResolve} />)
    // remote arg placeholder is shown; restored cleartext is not.
    expect(screen.getByText(/<<EMAIL_1>>/)).toBeInTheDocument()
    expect(screen.queryByText(/ada@example\.com/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /approve/i }))
    expect(onResolve).toHaveBeenCalledWith('appr-1', true)
    fireEvent.click(screen.getByRole('button', { name: /deny/i }))
    expect(onResolve).toHaveBeenCalledWith('appr-1', false)
  })

  it('renders nothing once resolved (status != pending)', () => {
    const { container } = render(
      <ToolApprovalPrompt approval={makeApproval({ status: 'approved' })} onResolve={() => {}} />,
    )
    expect(container.querySelector('[data-testid="tool-approval-prompt"]')).toBeNull()
  })
})
