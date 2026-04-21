import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { EntitySummary } from './EntitySummary'
import type { PrivacySnapshot } from '@/features/privacy/types'

const snapshot: PrivacySnapshot = {
  total_entities: 3,
  entity_counts: [
    { entity_type: 'person_name', severity: 'high', count: 1 },
    { entity_type: 'email', severity: 'medium', count: 1 },
    { entity_type: 'location', severity: 'low', count: 1 },
  ],
  entities: [
    {
      placeholder: '<<EMAIL_1>>',
      entity_type: 'email',
      severity: 'medium',
      canonical: 'alice@example.com',
      aliases: ['alice@example.com', 'Alice@Example.com'],
      value: 'alice@example.com',
      created_turn: 'turn-1',
      last_seen_turn: 'turn-2',
    },
    {
      placeholder: '<<PERSON_1>>',
      entity_type: 'person_name',
      severity: 'high',
      canonical: 'Alice Johnson',
      aliases: ['Alice Johnson', 'Alice J.'],
      value: 'Alice Johnson',
      created_turn: 'turn-1',
      last_seen_turn: 'turn-3',
    },
    {
      placeholder: '<<LOCATION_1>>',
      entity_type: 'location',
      severity: 'low',
      canonical: 'Seattle',
      aliases: ['Seattle'],
      value: 'Seattle',
      created_turn: 'turn-2',
      last_seen_turn: 'turn-2',
    },
  ],
}

const emptySnapshot: PrivacySnapshot = {
  total_entities: 0,
  entity_counts: [],
  entities: [],
}

describe('EntitySummary', () => {
  it('filters entities by canonical or placeholder and preserves severity-first ordering', async () => {
    const user = userEvent.setup()
    render(<EntitySummary snapshot={snapshot} />)

    const rows = screen.getAllByTestId('entity-row')
    expect(rows).toHaveLength(3)
    expect(within(rows[0]!).getByText('Alice Johnson')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('alice@example.com')).toBeInTheDocument()
    expect(within(rows[2]!).getByText('Seattle')).toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: /search entities/i }), '<<')

    const placeholderRows = screen.getAllByTestId('entity-row')
    expect(placeholderRows).toHaveLength(3)
    expect(within(placeholderRows[0]!).getByText('Alice Johnson')).toBeInTheDocument()

    await user.clear(screen.getByRole('textbox', { name: /search entities/i }))
    await user.type(screen.getByRole('textbox', { name: /search entities/i }), 'example')

    const filteredRows = screen.getAllByTestId('entity-row')
    expect(filteredRows).toHaveLength(1)
    expect(within(filteredRows[0]!).getByText('alice@example.com')).toBeInTheDocument()
  })

  it('renders compact rows by default and expands details per row', async () => {
    const user = userEvent.setup()
    render(<EntitySummary snapshot={snapshot} />)

    expect(screen.queryByText(/Normalized value:/i)).not.toBeInTheDocument()

    const row = screen.getAllByTestId('entity-row')[0]!
    const detailsButton = within(row).getByRole('button', { name: 'Show details for Alice Johnson' })
    await user.click(detailsButton)

    expect(within(row).getByRole('button', { name: 'Hide details for Alice Johnson' })).toHaveAttribute('aria-expanded', 'true')
    expect(within(row).getByText('Aliases 2')).toBeInTheDocument()
    expect(within(row).getByText('Created turn-1')).toBeInTheDocument()
    expect(within(row).getByText('Last seen turn-3')).toBeInTheDocument()
    expect(within(row).getByText(/Normalized value:/i)).toBeInTheDocument()
    expect(within(row).getByText('Alice J.')).toBeInTheDocument()

    await user.click(within(row).getByRole('button', { name: 'Hide details for Alice Johnson' }))
    expect(screen.queryByText(/Normalized value:/i)).not.toBeInTheDocument()
  })

  it('uses rounded stat cards with the same inner card styling in empty state', () => {
    render(<EntitySummary snapshot={emptySnapshot} />)

    const entitiesStat = screen.getByText('Entities').parentElement
    const typesStat = screen.getByText('Types').parentElement
    const highStat = screen.getByText('High').parentElement

    expect(entitiesStat).toHaveClass('rounded-md', 'bg-card/70')
    expect(typesStat).toHaveClass('rounded-md', 'bg-card/70')
    expect(highStat).toHaveClass('rounded-md', 'bg-card/70')
  })
})
