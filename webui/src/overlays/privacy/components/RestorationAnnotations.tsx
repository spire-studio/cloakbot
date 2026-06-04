import { AnnotatedMarkdown } from '@/overlays/privacy/lib/annotated-markdown'
import { usePrivacyAnnotations } from '@/overlays/privacy/context/PrivacyStateProvider'

/**
 * Render-prop slot mounted on ``MessageBubble`` for assistant turns.
 *
 * If the privacy lane recorded restoration annotations for *messageId*, this
 * renders the assistant reply through :func:`AnnotatedMarkdown` (placeholder ↔
 * real-value highlights) and returns it; otherwise it returns ``null`` so the
 * bubble falls back to its normal ``MarkdownText`` rendering. Keeping it a slot
 * means the upstream bubble needs only a ~3-line additive hook.
 *
 * The annotations index the locally-restored display string only and are never
 * echoed back to the model, so this view cannot reintroduce a placeholder into
 * remote history.
 */
export function RestorationAnnotations({
  messageId,
  content,
}: {
  messageId: string | undefined
  content: string
}) {
  const annotations = usePrivacyAnnotations(messageId)
  if (annotations.length === 0) return null
  return (
    <div data-testid="restoration-annotations">
      <AnnotatedMarkdown content={content} annotations={annotations} />
    </div>
  )
}
