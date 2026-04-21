import { Info, Search } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Chip } from '@/components/ui/chip'
import { Input } from '@/components/ui/input'
import type { PrivacySnapshot, PrivacySummary } from '@/features/privacy/types'
import { BRAND_NAME } from '@/shared/constants/brand'

function formatEntityLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function severityRank(severity: PrivacySummary['severity']) {
  if (severity === 'high') {
    return 0
  }
  if (severity === 'medium') {
    return 1
  }
  return 2
}

function privacySeverityClasses(severity: PrivacySummary['severity']) {
  if (severity === 'high') {
    return 'border-[var(--privacy-high-border)] bg-[var(--privacy-high-bg)] text-[var(--privacy-high-text)]'
  }
  if (severity === 'medium') {
    return 'border-[var(--privacy-medium-border)] bg-[var(--privacy-medium-bg)] text-[var(--privacy-medium-text)]'
  }
  return 'border-[var(--privacy-low-border)] bg-[var(--privacy-low-bg)] text-[var(--privacy-low-text)]'
}

type EntitySummaryProps = {
  snapshot: PrivacySnapshot
}

export function EntitySummary({ snapshot }: EntitySummaryProps) {
  const [search, setSearch] = useState('')
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set())

  const orderedCounts = useMemo(
    () =>
      [...snapshot.entity_counts].sort((left, right) => {
        const severityDiff = severityRank(left.severity) - severityRank(right.severity)
        if (severityDiff !== 0) {
          return severityDiff
        }

        if (left.count !== right.count) {
          return right.count - left.count
        }

        return left.entity_type.localeCompare(right.entity_type)
      }),
    [snapshot.entity_counts],
  )

  const orderedEntities = useMemo(
    () =>
      [...snapshot.entities].sort((left, right) => {
        const severityDiff = severityRank(left.severity) - severityRank(right.severity)
        if (severityDiff !== 0) {
          return severityDiff
        }

        return left.canonical.localeCompare(right.canonical)
      }),
    [snapshot.entities],
  )

  const normalizedSearch = search.trim().toLowerCase()
  const filteredEntities = useMemo(() => {
    if (!normalizedSearch) {
      return orderedEntities
    }

    return orderedEntities.filter((entity) => {
      const canonical = entity.canonical.toLowerCase()
      const placeholder = entity.placeholder.toLowerCase()
      return canonical.includes(normalizedSearch) || placeholder.includes(normalizedSearch)
    })
  }, [normalizedSearch, orderedEntities])

  const distinctTypeCount = new Set(snapshot.entities.map((entity) => entity.entity_type)).size
  const highSeverityCount = snapshot.entities.filter((entity) => entity.severity === 'high').length

  const toggleExpanded = (placeholder: string) => {
    setExpandedRows((current) => {
      const next = new Set(current)
      if (next.has(placeholder)) {
        next.delete(placeholder)
      } else {
        next.add(placeholder)
      }
      return next
    })
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-md border border-border/70 bg-card/70 px-3 py-2">
          <div className="text-[11px] text-muted-foreground">Entities</div>
          <div className="mt-1 text-sm font-semibold text-foreground">{snapshot.total_entities}</div>
        </div>
        <div className="rounded-md border border-border/70 bg-card/70 px-3 py-2">
          <div className="text-[11px] text-muted-foreground">Types</div>
          <div className="mt-1 text-sm font-semibold text-foreground">{distinctTypeCount}</div>
        </div>
        <div className="rounded-md border border-border/70 bg-card/70 px-3 py-2">
          <div className="text-[11px] text-muted-foreground">High</div>
          <div className="mt-1 text-sm font-semibold text-foreground">{highSeverityCount}</div>
        </div>
      </div>

      {orderedCounts.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-3">
          <div className="text-[11px] tracking-[0.08em] text-muted-foreground">Density by type</div>
          <div className="mt-2 space-y-2">
            {orderedCounts.map((summary) => (
              <div
                key={`${summary.entity_type}-${summary.severity}`}
                className="flex items-center justify-between gap-3 rounded-md border border-border bg-secondary/65 px-2.5 py-1.5"
              >
                <div className="min-w-0 text-sm text-foreground">
                  {formatEntityLabel(summary.entity_type)}
                </div>
                <div className="flex items-center gap-2">
                  <Chip className={privacySeverityClasses(summary.severity)}>{summary.severity}</Chip>
                  <Chip>x{summary.count}</Chip>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {orderedEntities.length > 0 && (
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search canonical or placeholder"
            aria-label="Search entities"
            className="h-9 pl-9"
          />
        </div>
      )}

      {orderedEntities.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card px-4 py-5 text-sm leading-[1.6] text-muted-foreground">
          Detected entities will appear here after {BRAND_NAME} finishes a response.
        </div>
      ) : filteredEntities.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card px-4 py-5 text-sm leading-[1.6] text-muted-foreground">
          No entities match this search.
        </div>
      ) : (
        <div className="space-y-2 rounded-xl bg-card/80">
          {filteredEntities.map((entity) => {
            const extraAliases = entity.aliases.filter((alias) => alias !== entity.canonical)
            const isExpanded = expandedRows.has(entity.placeholder)

            return (
              <div
                key={entity.placeholder}
                data-testid="entity-row"
                className="rounded-xl border border-border bg-card px-3 py-2.5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-foreground">{entity.canonical}</div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">{entity.placeholder}</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {formatEntityLabel(entity.entity_type)}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Chip size="roomy" className={privacySeverityClasses(entity.severity)}>
                      {entity.severity}
                    </Chip>
                    <button
                      type="button"
                      className="flex h-7 w-7 items-center justify-center rounded-md border border-border/70 text-muted-foreground transition-colors hover:bg-secondary"
                      onClick={() => toggleExpanded(entity.placeholder)}
                      aria-expanded={isExpanded}
                      aria-controls={`entity-details-${entity.placeholder}`}
                      aria-label={isExpanded ? `Hide details for ${entity.canonical}` : `Show details for ${entity.canonical}`}
                    >
                      <Info className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div id={`entity-details-${entity.placeholder}`} className="mt-2 space-y-2 border-t border-border/60 pt-2 text-[11px]">
                    <div className="flex flex-wrap items-center gap-1.5 text-muted-foreground">
                      <Chip>Aliases {entity.aliases.length}</Chip>
                      {entity.created_turn && (
                        <Chip>Created {entity.created_turn}</Chip>
                      )}
                      {entity.last_seen_turn && (
                        <Chip>Last seen {entity.last_seen_turn}</Chip>
                      )}
                    </div>

                    {extraAliases.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {extraAliases.map((alias) => (
                          <Chip key={`${entity.placeholder}-${alias}`} variant="fill" size="roomy">
                            {alias}
                          </Chip>
                        ))}
                      </div>
                    )}

                    {entity.value !== null && entity.value !== undefined && (
                      <div className="text-muted-foreground">
                        Normalized value: <span className="font-medium text-foreground">{String(entity.value)}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
