import { Paperclip, Sparkles } from 'lucide-react'
import { useState, type SyntheticEvent } from 'react'

import { Chip } from '@/components/ui/chip'
import { DEMO_SCENARIOS, type DemoScenario } from '@/features/chat/lib/demo-scenarios'
import { cn } from '@/lib/utils'

type DemoLauncherProps = {
  onLoadScenario: (scenario: DemoScenario) => void
  disabled?: boolean
  className?: string
}

export function DemoLauncher({ onLoadScenario, disabled = false, className }: DemoLauncherProps) {
  return (
    <div className={cn('w-full', className)}>
      <div className="mb-3 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
        <Sparkles className="h-3 w-3" />
        <span>Try a built-in scenario</span>
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        {DEMO_SCENARIOS.map((scenario) => (
          <ScenarioCard
            key={scenario.id}
            scenario={scenario}
            disabled={disabled}
            onClick={() => onLoadScenario(scenario)}
          />
        ))}
      </div>
    </div>
  )
}

type ScenarioCardProps = {
  scenario: DemoScenario
  disabled: boolean
  onClick: () => void
}

function ScenarioCard({ scenario, disabled, onClick }: ScenarioCardProps) {
  const [thumbnailFailed, setThumbnailFailed] = useState(false)
  const Icon = scenario.icon
  const handleThumbnailError = (event: SyntheticEvent<HTMLImageElement>) => {
    event.currentTarget.style.display = 'none'
    setThumbnailFailed(true)
  }
  const showThumbnail = Boolean(scenario.thumbnail) && !thumbnailFailed

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'group flex flex-col gap-2.5 rounded-2xl border border-border bg-card p-3 text-left transition-all duration-150',
        'hover:border-[var(--surface-outline-strong)] hover:bg-[var(--surface-subtle)] hover:shadow-[0_8px_24px_var(--shadow-soft)]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
      )}
    >
      <div className="flex h-20 w-full items-center justify-center overflow-hidden rounded-lg border border-border/70 bg-[var(--surface-subtle)]">
        {showThumbnail ? (
          <img
            src={scenario.thumbnail}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            onError={handleThumbnailError}
          />
        ) : (
          <Icon className="h-7 w-7 text-muted-foreground transition-colors group-hover:text-foreground" />
        )}
      </div>

      <div className="space-y-1">
        <div className="text-[13px] font-semibold leading-tight text-foreground">{scenario.title}</div>
        <div className="line-clamp-2 text-[11.5px] leading-[1.45] text-muted-foreground">
          {scenario.blurb}
        </div>
      </div>

      <Chip className="self-start gap-1 truncate text-[10.5px]">
        <Paperclip className="h-2.5 w-2.5" />
        <span className="truncate">{scenario.attachmentLabel}</span>
      </Chip>
    </button>
  )
}
