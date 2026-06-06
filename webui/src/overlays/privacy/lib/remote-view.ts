import type { PrivacyAnnotation } from '@/overlays/privacy/types'

/**
 * Derive the "Remote" (placeholder) view of an assistant reply from its
 * locally-restored "Local" content + restoration annotations.
 *
 * Each annotation's restored span (its cleartext, ``content[start, end)``) is
 * swapped back to the ``<<TAG_N>>`` placeholder the remote model actually saw.
 * Returns the rebuilt string plus annotations re-pointed at the placeholder
 * spans (same entity metadata), so the Remote view can stay highlighted.
 *
 * Pure + reversible: unchanged text is identical between the two views; only the
 * annotated spans differ. No backend round-trip — the annotations are a complete
 * placeholder<->value bijection for the spans that changed. Overlapping or
 * out-of-range spans are skipped rather than allowed to corrupt the string.
 */
export function buildRemoteView(
  content: string,
  annotations: PrivacyAnnotation[],
): { content: string; annotations: PrivacyAnnotation[] } {
  const sorted = [...annotations].sort((a, b) => a.start - b.start)
  let remote = ''
  let cursor = 0
  const remoteAnnotations: PrivacyAnnotation[] = []
  for (const ann of sorted) {
    if (ann.start < cursor || ann.start >= ann.end || ann.end > content.length) continue
    remote += content.slice(cursor, ann.start)
    const start = remote.length
    remote += ann.placeholder
    remoteAnnotations.push({ ...ann, text: ann.placeholder, start, end: remote.length })
    cursor = ann.end
  }
  remote += content.slice(cursor)
  return { content: remote, annotations: remoteAnnotations }
}
