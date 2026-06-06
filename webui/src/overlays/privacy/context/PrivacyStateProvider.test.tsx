import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  PrivacyStateProvider,
  usePrivacyState,
} from '@/overlays/privacy/context/PrivacyStateProvider'
import type { PrivacyEvent, PrivacyLaneClient } from '@/overlays/privacy/lib/privacy-client-lane'
import { classifyPrivacyFrame } from '@/overlays/privacy/lib/privacy-client-lane'
import { makeApproval, makePayload, makeSnapshot } from '@/overlays/privacy/lib/__fixtures__'
import type { PrivacyPayload } from '@/overlays/privacy/types'

/** A controllable fake client whose onChat sink we can drive frame-by-frame. */
function makeFakeClient() {
  const sinks = new Map<string, (ev: unknown) => void>()
  const client: PrivacyLaneClient = {
    onChat(chatId, handler) {
      sinks.set(chatId, handler)
      return () => sinks.delete(chatId)
    },
  }
  return {
    client,
    emit(chatId: string, frame: unknown) {
      act(() => {
        sinks.get(chatId)?.(frame)
      })
    },
    hasSubscriber: (chatId: string) => sinks.has(chatId),
  }
}

function StatsProbe() {
  const { stats, snapshot, turns } = usePrivacyState()
  return (
    <div>
      <span data-testid="total">{stats.totalEntities}</span>
      <span data-testid="high">{stats.highSeverityCount}</span>
      <span data-testid="blocked">{stats.blockedSpans}</span>
      <span data-testid="entities">{snapshot.entities.length}</span>
      <span data-testid="turns">{turns.length}</span>
    </div>
  )
}

describe('PrivacyStateProvider', () => {
  it('accumulates snapshot + turn + annotations from a payload frame', () => {
    const fake = makeFakeClient()
    render(
      <PrivacyStateProvider client={fake.client} chatId="c1">
        <StatsProbe />
      </PrivacyStateProvider>,
    )

    fake.emit('c1', {
      event: 'message',
      chat_id: 'c1',
      text: 'done',
      reply_to: 'm1',
      agent_ui: { kind: 'privacy', privacy: makePayload() },
    })

    expect(screen.getByTestId('total').textContent).toBe('2')
    expect(screen.getByTestId('high').textContent).toBe('1')
    expect(screen.getByTestId('turns').textContent).toBe('1')
    // remotePrompt has <<PERSON_1>> x2 + <<EMAIL_1>> x1 = 3 placeholders, plus
    // total_entities (2) seeds the blocked counter.
    expect(Number(screen.getByTestId('blocked').textContent)).toBeGreaterThanOrEqual(3)
  })

  it('merges a later snapshot frame over the accumulated state', () => {
    const fake = makeFakeClient()
    render(
      <PrivacyStateProvider client={fake.client} chatId="c1">
        <StatsProbe />
      </PrivacyStateProvider>,
    )
    fake.emit('c1', { event: 'privacy_snapshot', chat_id: 'c1', data: makeSnapshot({ total_entities: 5 }) })
    expect(screen.getByTestId('total').textContent).toBe('5')
  })

  it('resets state and re-subscribes when the active chat changes (isolation)', () => {
    const fake = makeFakeClient()
    const { rerender } = render(
      <PrivacyStateProvider client={fake.client} chatId="c1">
        <StatsProbe />
      </PrivacyStateProvider>,
    )
    fake.emit('c1', { event: 'privacy_snapshot', chat_id: 'c1', data: makeSnapshot({ total_entities: 9 }) })
    expect(screen.getByTestId('total').textContent).toBe('9')

    rerender(
      <PrivacyStateProvider client={fake.client} chatId="c2">
        <StatsProbe />
      </PrivacyStateProvider>,
    )
    // Switching chats wipes the previous session's entities.
    expect(screen.getByTestId('total').textContent).toBe('0')
    expect(fake.hasSubscriber('c2')).toBe(true)
  })

  it('records tool approvals carried on a payload turn', () => {
    const fake = makeFakeClient()
    function ApprovalProbe() {
      const { approvals } = usePrivacyState()
      return <span data-testid="approvals">{approvals.length}</span>
    }
    render(
      <PrivacyStateProvider client={fake.client} chatId="c1">
        <ApprovalProbe />
      </PrivacyStateProvider>,
    )
    const payload = makePayload()
    payload.privacyTurn.toolApprovals = [makeApproval()]
    fake.emit('c1', { event: 'tool_approval', chat_id: 'c1', approval: makeApproval() })
    expect(screen.getByTestId('approvals').textContent).toBe('1')
  })

  it('rehydrates inspector state from the persisted privacy log on mount', async () => {
    const fake = makeFakeClient()
    const loadHistory = () => Promise.resolve([makePayload()])
    render(
      <PrivacyStateProvider client={fake.client} chatId="c1" loadHistory={loadHistory}>
        <StatsProbe />
      </PrivacyStateProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('turns').textContent).toBe('1'))
    expect(screen.getByTestId('total').textContent).toBe('2')
    expect(screen.getByTestId('entities').textContent).toBe('2')
  })

  it('does not let stale persisted history clobber a fresher live turn', async () => {
    const fake = makeFakeClient()
    let resolveHistory: (payloads: PrivacyPayload[]) => void = () => {}
    const loadHistory = () =>
      new Promise<PrivacyPayload[]>((resolve) => {
        resolveHistory = resolve
      })
    render(
      <PrivacyStateProvider client={fake.client} chatId="c1" loadHistory={loadHistory}>
        <StatsProbe />
      </PrivacyStateProvider>,
    )
    // A live turn lands before the async history fetch resolves.
    fake.emit('c1', {
      event: 'message',
      chat_id: 'c1',
      text: 'done',
      reply_to: 'm1',
      agent_ui: { kind: 'privacy', privacy: makePayload({ privacy: makeSnapshot({ total_entities: 7 }) }) },
    })
    expect(screen.getByTestId('total').textContent).toBe('7')
    // History resolves with the SAME turnId but a stale snapshot -> skipped.
    await act(async () => {
      resolveHistory([makePayload({ privacy: makeSnapshot({ total_entities: 2 }) })])
    })
    expect(screen.getByTestId('total').textContent).toBe('7')
    expect(screen.getByTestId('turns').textContent).toBe('1')
  })

  it('falls back to empty state outside a provider', () => {
    function BareProbe() {
      const { stats } = usePrivacyState()
      return <span data-testid="bare">{stats.totalEntities}</span>
    }
    render(<BareProbe />)
    expect(screen.getByTestId('bare').textContent).toBe('0')
  })

  it('classifyPrivacyFrame and the provider agree on the decoded shape', () => {
    const frame = { event: 'privacy_snapshot', chat_id: 'c1', data: makeSnapshot() }
    const decoded = classifyPrivacyFrame(frame) as PrivacyEvent
    expect(decoded.kind).toBe('snapshot')
  })
})
