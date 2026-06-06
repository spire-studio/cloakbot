import { type ReactNode, useState } from 'react'

import { cn } from '@/lib/utils'
import { AnnotatedMarkdown } from '@/overlays/privacy/lib/annotated-markdown'
import { buildRemoteView } from '@/overlays/privacy/lib/remote-view'
import { PRIVACY_HIGHLIGHT_CLASS_NAME } from '@/overlays/privacy/lib/severity'
import type { PrivacyAnnotation } from '@/overlays/privacy/types'

/**
 * Assistant reply with the CloakBot privacy Diff toggle.
 *
 * - **Local** (default): the locally-restored reply with real values, each
 *   restored entity highlighted + hoverable (placeholder ↔ value) via
 *   :func:`AnnotatedMarkdown`.
 * - **Remote**: the exact placeholdered text the remote model saw, rendered as
 *   plain highlighted text (markdown would mangle the ``<<TAG_N>>`` tokens).
 *
 * Both views are derived on the client from one restored string + its
 * annotations (a complete bijection). The vault never leaves the backend and no
 * placeholder is ever echoed back to the model — these spans index the local
 * display string only.
 */
/**
 * The "N restored entities · Local | Remote" control row. Split out from the
 * body so callers (e.g. the assistant footer in ``MessageBubble``) can place it
 * next to the copy button while the body renders above. Controlled: the caller
 * owns ``showRemote`` so the toggle and the body it drives can live apart.
 */
export function RestorationDiffToggle({
  count,
  showRemote,
  onToggle,
  className,
}: {
  count: number
  showRemote: boolean
  onToggle: (showRemote: boolean) => void
  className?: string
}) {
  if (count === 0) return null
  return (
    <div className={cn('flex items-center gap-2 text-[11px] text-muted-foreground', className)}>
      <span>
        {count} restored {count === 1 ? 'entity' : 'entities'}
      </span>
      <div
        className="inline-flex overflow-hidden rounded-md border border-border"
        role="group"
        aria-label="Local versus remote view"
      >
        <button
          type="button"
          aria-pressed={!showRemote}
          onClick={() => onToggle(false)}
          className={cn(
            'px-2 py-0.5 transition-colors',
            !showRemote
              ? 'bg-sky-100 font-medium text-sky-900 dark:bg-sky-400/20 dark:text-sky-100'
              : 'hover:bg-muted',
          )}
        >
          Local
        </button>
        <button
          type="button"
          aria-pressed={showRemote}
          onClick={() => onToggle(true)}
          className={cn(
            'border-l border-border px-2 py-0.5 transition-colors',
            showRemote
              ? 'bg-amber-100 font-medium text-amber-900 dark:bg-amber-400/20 dark:text-amber-100'
              : 'hover:bg-muted',
          )}
        >
          Remote
        </button>
      </div>
    </div>
  )
}

/** The reply body for the active Diff view (Local annotated vs. Remote placeholder). */
export function RestorationBody({
  content,
  annotations,
  showRemote,
}: {
  content: string
  annotations: PrivacyAnnotation[]
  showRemote: boolean
}) {
  if (annotations.length === 0 || !showRemote) {
    return <AnnotatedMarkdown content={content} annotations={annotations} />
  }
  return <RemotePlaceholderText {...buildRemoteView(content, annotations)} />
}

/**
 * Self-contained Diff view: toggle row above the body. Retained for standalone
 * use / tests; ``MessageBubble`` instead composes :func:`RestorationDiffToggle`
 * (in the footer) and :func:`RestorationBody` (in the reply slot) with a single
 * lifted ``showRemote`` state.
 */
export function RestorationAnnotations({
  content,
  annotations,
}: {
  content: string
  annotations: PrivacyAnnotation[]
}) {
  const [showRemote, setShowRemote] = useState(false)
  if (annotations.length === 0) {
    return <AnnotatedMarkdown content={content} annotations={annotations} />
  }
  return (
    <div data-testid="restoration-annotations">
      <RestorationDiffToggle
        count={annotations.length}
        showRemote={showRemote}
        onToggle={setShowRemote}
        className="mb-1.5"
      />
      <RestorationBody content={content} annotations={annotations} showRemote={showRemote} />
    </div>
  )
}

/**
 * Render the placeholdered remote string as plain text with the ``<<TAG_N>>``
 * spans highlighted. Plain (not markdown) on purpose: this is the literal string
 * the model received, and markdown would parse ``<<…>>`` as an HTML tag and drop
 * it. Native ``title`` exposes the placeholder ↔ real-value mapping on hover.
 */
function RemotePlaceholderText({
  content,
  annotations,
}: {
  content: string
  annotations: PrivacyAnnotation[]
}) {
  const sorted = [...annotations].sort((a, b) => a.start - b.start)
  const parts: ReactNode[] = []
  let cursor = 0
  sorted.forEach((ann, index) => {
    if (ann.start < cursor || ann.start >= ann.end || ann.end > content.length) return
    if (ann.start > cursor) parts.push(content.slice(cursor, ann.start))
    parts.push(
      <span
        key={`${ann.placeholder}-${index}`}
        className={PRIVACY_HIGHLIGHT_CLASS_NAME}
        title={`${ann.placeholder} → ${ann.canonical}`}
      >
        {content.slice(ann.start, ann.end)}
      </span>,
    )
    cursor = ann.end
  })
  if (cursor < content.length) parts.push(content.slice(cursor))
  // Match AnnotatedMarkdown's wrapper (`prose …`) so the font size / line height
  // are identical across the Local↔Remote toggle; ``whitespace-pre-wrap`` keeps
  // the raw model-facing string's own line breaks.
  return (
    <div className="prose max-w-none whitespace-pre-wrap break-words text-current dark:prose-invert">
      {parts}
    </div>
  )
}
