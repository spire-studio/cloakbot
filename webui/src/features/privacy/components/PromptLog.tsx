import type { PrivacyTurn } from '@/features/privacy/types'
import { BRAND_NAME } from '@/shared/constants/brand'

type PromptLogProps = {
  turns: PrivacyTurn[]
}

export function PromptLog({ turns }: PromptLogProps) {
  if (turns.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/80 bg-card/70 px-4 py-5 text-sm text-muted-foreground">
        Sanitized prompts will appear here after {BRAND_NAME} finishes a response.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {turns.map((turn, index) => (
        <div key={turn.turnId} className="rounded-2xl border border-border/70 bg-card/85 p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-foreground">Turn {index + 1}</div>
            <div className="rounded-md bg-secondary px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-secondary-foreground">
              {turn.intent}
            </div>
          </div>
          <pre className="mt-3 whitespace-pre-wrap break-words rounded-xl bg-background/80 px-3 py-3 font-mono text-xs leading-6 text-foreground">
            {turn.remotePrompt}
          </pre>
        </div>
      ))}
    </div>
  )
}
