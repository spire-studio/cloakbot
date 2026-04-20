import type { PrivacySnapshot, PrivacySummary } from '@/features/privacy/types'
import { cn } from '@/lib/utils'
import { BRAND_NAME } from '@/shared/constants/brand'

function formatEntityLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function privacySeverityClasses(severity: PrivacySummary['severity']) {
  if (severity === 'high') {
    return 'border-rose-200 bg-rose-50 text-rose-700'
  }
  if (severity === 'medium') {
    return 'border-amber-200 bg-amber-50 text-amber-700'
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-700'
}

type EntitySummaryProps = {
  snapshot: PrivacySnapshot
}

export function EntitySummary({ snapshot }: EntitySummaryProps) {
  return (
    <div className="space-y-4">
      {snapshot.entity_counts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {snapshot.entity_counts.map((summary) => (
            <div
              key={`${summary.entity_type}-${summary.severity}`}
              className={cn(
                'rounded-md border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em]',
                privacySeverityClasses(summary.severity),
              )}
            >
              {formatEntityLabel(summary.entity_type)} x{summary.count}
            </div>
          ))}
        </div>
      )}

      {snapshot.entities.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border/80 bg-card/70 px-4 py-5 text-sm text-muted-foreground">
          Detected entities will appear here after {BRAND_NAME} finishes a response.
        </div>
      ) : (
        snapshot.entities.map((entity) => {
          const extraAliases = entity.aliases.filter((alias) => alias !== entity.canonical)
          return (
            <div key={entity.placeholder} className="rounded-2xl border border-border/70 bg-card/85 p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-foreground">{entity.canonical}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{entity.placeholder}</div>
                </div>
                <div
                  className={cn(
                    'shrink-0 rounded-md border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]',
                    privacySeverityClasses(entity.severity),
                  )}
                >
                  {formatEntityLabel(entity.entity_type)}
                </div>
              </div>

              {extraAliases.length > 0 && (
                <div className="mt-3">
                  <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Aliases
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {extraAliases.map((alias) => (
                      <span
                        key={`${entity.placeholder}-${alias}`}
                        className="rounded-md bg-secondary px-2.5 py-1 text-xs text-secondary-foreground"
                      >
                        {alias}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {entity.value !== null && entity.value !== undefined && (
                <div className="mt-3 text-xs text-muted-foreground">
                  Normalized value: <span className="font-medium text-foreground">{String(entity.value)}</span>
                </div>
              )}
            </div>
          )
        })
      )}
    </div>
  )
}
