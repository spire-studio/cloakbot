/**
 * Severity → Tailwind class maps for the privacy overlay.
 *
 * The salvaged components referenced bespoke ``--privacy-*`` CSS variables that
 * lived in the deleted SPA's ``index.css``. To keep the overlay self-contained
 * (no edit to upstream ``globals.css``), severities map to fixed Tailwind color
 * utilities here. High = rose, Medium = amber, Low = slate.
 */
import type { Severity } from '@/overlays/privacy/types'

/** Badge/chip classes for an entity severity. */
export function severityClasses(severity: Severity): string {
  if (severity === 'high') {
    return 'border-rose-300 bg-rose-100 text-rose-800 dark:border-rose-500/40 dark:bg-rose-500/15 dark:text-rose-200'
  }
  if (severity === 'medium') {
    return 'border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200'
  }
  return 'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-500/40 dark:bg-slate-500/15 dark:text-slate-200'
}

/** Inline-highlight classes for a restored span in the assistant reply. */
export const PRIVACY_HIGHLIGHT_CLASS_NAME =
  'rounded-[0.32rem] border border-sky-300/70 bg-sky-100/70 px-[0.34rem] py-[0.1rem] text-inherit transition-colors hover:bg-sky-200/70 dark:border-sky-400/40 dark:bg-sky-400/15 dark:hover:bg-sky-400/25'

/** Sentinel the backend substitutes for stripped raw values (non-localhost). */
export const REDACTED_SENTINEL = '[redacted: localhost-only]'

/** Human label for an entity type token (``EMAIL_ADDRESS`` → ``email address``). */
export function formatEntityLabel(value: string): string {
  return value.replaceAll('_', ' ').toLowerCase()
}

/** Rank used to sort severities high → low. */
export function severityRank(severity: Severity): number {
  if (severity === 'high') return 0
  if (severity === 'medium') return 1
  return 2
}
