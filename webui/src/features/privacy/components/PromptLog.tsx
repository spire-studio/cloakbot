import { ChevronDown, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Chip } from '@/components/ui/chip'
import type { PrivacyTurn } from '@/features/privacy/types'
import { cn } from '@/lib/utils'
import { BRAND_NAME } from '@/shared/constants/brand'

type PromptLogProps = {
  turns: PrivacyTurn[]
}

export function PromptLog({ turns }: PromptLogProps) {
  const [expandedTurnId, setExpandedTurnId] = useState<string | null>(null)

  const turnOrder = useMemo(
    () =>
      turns.map((turn, index) => ({
        ...turn,
        turnNumber: index + 1,
      })),
    [turns],
  )

  if (turns.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card px-4 py-5 text-sm leading-[1.6] text-muted-foreground">
        Sanitized prompts will appear here after {BRAND_NAME} finishes a response.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {turnOrder.map((turn, index) => {
        const fallbackExpandedTurnId = turnOrder[turnOrder.length - 1]?.turnId ?? null
        const currentExpandedTurnId =
          expandedTurnId && turnOrder.some((item) => item.turnId === expandedTurnId)
            ? expandedTurnId
            : fallbackExpandedTurnId
        const isExpanded = currentExpandedTurnId === turn.turnId
        const isNewest = index === turnOrder.length - 1

        return (
          <section key={turn.turnId} className="overflow-hidden rounded-xl border border-border bg-card">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              onClick={() => setExpandedTurnId((current) => (current === turn.turnId ? null : turn.turnId))}
              aria-expanded={isExpanded}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <span>Turn {turn.turnNumber}</span>
                  {isNewest && <Chip variant="fill">Newest</Chip>}
                </div>
                <div className="mt-1 text-[12px] text-muted-foreground">
                  {turn.intent} · {turn.remotePrompt.length} chars · Sanitized
                </div>
              </div>
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
            </button>

            <div
              className={cn(
                'grid transition-[grid-template-rows,opacity] duration-200 ease-out',
                isExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-85',
              )}
            >
              <div className="overflow-hidden">
                <div className="border-t border-border/70 px-4 py-3">
                  <div className="mb-2 flex items-center gap-2">
                    <Chip variant="fill">Sanitized payload</Chip>
                  </div>
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-[var(--surface-subtle)] px-3 py-3 font-mono text-xs leading-6 text-foreground">
                    {turn.remotePrompt}
                  </pre>
                </div>
              </div>
            </div>
          </section>
        )
      })}
    </div>
  )
}
