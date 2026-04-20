import type { PrivacyTurn } from '@/features/privacy/types'

type ComputationLogProps = {
  turns: PrivacyTurn[]
}

export function ComputationLog({ turns }: ComputationLogProps) {
  const computationTurns = turns.filter((turn) => turn.localComputations.length > 0)

  if (computationTurns.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/80 bg-card/70 px-4 py-5 text-sm text-muted-foreground">
        Local computation steps will appear here for privacy math turns.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {computationTurns.map((turn) => (
        <div key={`computation-${turn.turnId}`} className="rounded-2xl border border-border/70 bg-card/85 p-4 shadow-sm">
          <div className="text-sm font-semibold text-foreground">
            Turn {turns.findIndex((item) => item.turnId === turn.turnId) + 1}
          </div>
          <div className="mt-3 space-y-3">
            {turn.localComputations.map((computation, computationIndex) => (
              <div key={`${turn.turnId}-${computation.snippet_index}`} className="rounded-xl bg-background/80 px-3 py-3">
                <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Computation {computationIndex + 1}
                </div>
                <div className="mt-2 font-mono text-xs leading-6 text-foreground">
                  {computation.resolved_expression} = {computation.formatted_result}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
