import { ChevronDown, ChevronRight } from 'lucide-react'
import { useMemo, useState } from 'react'

import { cn } from '@/lib/utils'
import { Chip, BRAND_NAME } from '@/overlays/privacy/lib/ui'
import type { PrivacyTurn } from '@/overlays/privacy/types'

type PromptLogProps = {
  turns: PrivacyTurn[]
}

/**
 * Per-turn log of the exact sanitized payload sent to the remote model.
 *
 * ``remotePrompt`` and ``sanitizedOutput`` are already placeholdered (what the
 * remote LLM saw), so this view is safe in both localhost and redacted
 * projections — it is the whole point of the overlay.
 */
export function PromptLog({ turns }: PromptLogProps) {
  const [expandedTurnId, setExpandedTurnId] = useState<string | null>(null)

  const turnOrder = useMemo(
    () => turns.map((turn, index) => ({ ...turn, turnNumber: index + 1 })),
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
        const toolResults = turn.toolResults ?? []
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
                  {turn.intent} · {turn.remotePrompt.length} chars · {toolResults.length} tool results · Sanitized
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
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 px-3 py-3 font-mono text-xs leading-6 text-foreground">
                    {turn.remotePrompt}
                  </pre>
                  {toolResults.length > 0 && (
                    <div className="mt-3 space-y-3">
                      {toolResults.map((result) => (
                        <section key={result.toolCallId} className="border-t border-border/70 pt-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Chip variant="fill">{result.toolName}</Chip>
                            <Chip>{result.wasSanitized ? 'Output sanitized' : 'No output entities'}</Chip>
                            {(result.visualRedactions?.length ?? 0) > 0 && (
                              <Chip>
                                Visual redaction ·{' '}
                                {result.visualRedactions?.reduce((total, item) => total + item.redactionBoxes, 0)} boxes
                              </Chip>
                            )}
                          </div>
                          <div className="mt-2 space-y-2">
                            <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 px-3 py-2 font-mono text-[11px] leading-5 text-muted-foreground">
                              {JSON.stringify(result.remoteArguments, null, 2)}
                            </pre>
                            {(result.visualRedactions?.length ?? 0) > 0 && (
                              <div className="rounded-md border border-border/70 bg-muted/50 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                                {result.visualRedactions?.map((item, visualIndex) => (
                                  <div key={`${item.sourcePath ?? 'visual'}-${visualIndex}`}>
                                    {item.status} · {item.detectedItems} detected · {item.redactionBoxes} boxes
                                    {item.labels.length > 0 && ` · ${item.labels.join(', ')}`}
                                  </div>
                                ))}
                              </div>
                            )}
                            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 px-3 py-2 font-mono text-xs leading-6 text-foreground">
                              {result.sanitizedOutput}
                            </pre>
                          </div>
                        </section>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>
        )
      })}
    </div>
  )
}
