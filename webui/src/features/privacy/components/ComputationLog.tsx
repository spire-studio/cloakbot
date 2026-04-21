import { Check, Copy } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Chip } from '@/components/ui/chip'
import type { PrivacyTurn } from '@/features/privacy/types'

type ComputationLogProps = {
  turns: PrivacyTurn[]
}

export function ComputationLog({ turns }: ComputationLogProps) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const copiedResetTimeoutRef = useRef<number | null>(null)
  const computationTurns = turns.filter((turn) => turn.localComputations.length > 0)
  const turnNumberById = useMemo(
    () => new Map(turns.map((turn, index) => [turn.turnId, index + 1])),
    [turns],
  )

  useEffect(() => {
    return () => {
      if (copiedResetTimeoutRef.current !== null) {
        window.clearTimeout(copiedResetTimeoutRef.current)
      }
    }
  }, [])

  if (computationTurns.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card px-4 py-5 text-sm leading-[1.6] text-muted-foreground">
        Local computation steps will appear here for privacy math turns.
      </div>
    )
  }

  const handleCopy = async (key: string, content: string) => {
    try {
      if (typeof navigator === 'undefined' || !navigator.clipboard) {
        return
      }

      await navigator.clipboard.writeText(content)
      setCopiedKey(key)

      if (copiedResetTimeoutRef.current !== null) {
        window.clearTimeout(copiedResetTimeoutRef.current)
      }

      copiedResetTimeoutRef.current = window.setTimeout(() => {
        setCopiedKey((current) => (current === key ? null : current))
        copiedResetTimeoutRef.current = null
      }, 1200)
    } catch {
      setCopiedKey((current) => (current === key ? null : current))
    }
  }

  return (
    <div className="space-y-4">
      {computationTurns.map((turn) => {
        const turnNumber = turnNumberById.get(turn.turnId) ?? 0

        return (
          <section key={`computation-${turn.turnId}`} className="rounded-xl border border-border bg-card p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="text-sm font-semibold text-foreground">Turn {turnNumber}</div>
              <Chip size="roomy">{turn.localComputations.length} steps</Chip>
            </div>

            <ol className="relative space-y-3 border-l border-border/70 pl-4">
              {turn.localComputations.map((computation, computationIndex) => {
                const copyKey = `${turn.turnId}-${computation.snippet_index}`
                const copyValue = `${computation.resolved_expression} = ${computation.formatted_result}`
                const isCopied = copiedKey === copyKey

                return (
                  <li
                    key={copyKey}
                    className="relative rounded-lg border border-border bg-[var(--surface-subtle)] px-3 py-3 before:absolute before:-left-[1.35rem] before:top-5 before:h-2 before:w-2 before:rounded-full before:bg-primary/70"
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                        <span>Step {computationIndex + 1}</span>
                        <Chip>Snippet #{computation.snippet_index}</Chip>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 rounded-md px-2 text-[11px]"
                        onClick={() => handleCopy(copyKey, copyValue)}
                        aria-label={`Copy computation ${computationIndex + 1} from turn ${turnNumber}`}
                      >
                        {isCopied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                        <span>{isCopied ? 'Copied' : 'Copy'}</span>
                      </Button>
                    </div>

                    <div className="font-mono text-xs leading-6 text-foreground">
                      {computation.resolved_expression}
                      <span className="mx-2 text-muted-foreground">=</span>
                      {computation.formatted_result}
                    </div>
                  </li>
                )
              })}
            </ol>
          </section>
        )
      })}
    </div>
  )
}
