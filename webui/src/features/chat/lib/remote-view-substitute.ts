import type { PrivacyEntity, PrivacySnapshot } from '@/features/privacy/types'

const PLACEHOLDER_PATTERN = /<<[A-Z][A-Z0-9_]*>>/g

/**
 * Replace every appearance of an entity's canonical value or alias with the
 * matching placeholder token, longest-needle first to avoid partial overlap.
 *
 * This is what the remote model would have seen — same string the sanitizer
 * sent over the wire, reconstructed client-side from the privacy snapshot.
 */
export function substituteEntities(content: string, entities: PrivacyEntity[]): string {
  if (!content || entities.length === 0) {
    return content
  }

  type Needle = { needle: string; placeholder: string }
  const needles: Needle[] = []
  for (const entity of entities) {
    const seen = new Set<string>()
    for (const candidate of [entity.canonical, ...entity.aliases]) {
      if (!candidate || seen.has(candidate)) {
        continue
      }
      seen.add(candidate)
      needles.push({ needle: candidate, placeholder: entity.placeholder })
    }
  }

  // Longest needle first so "John Doe" wins over "John".
  needles.sort((left, right) => right.needle.length - left.needle.length)

  let result = content
  for (const { needle, placeholder } of needles) {
    const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    // ASCII word-boundary lookbehind/lookahead so a short numeric needle
    // like "6" doesn't match the "6" inside "2026". The boundary is
    // ASCII-only on purpose — for Chinese/Unicode entity values the
    // lookbehind/lookahead never sees an ASCII word char, so legitimate
    // substring matches like 姓<<PERSON_1>>的 still work.
    result = result.replace(
      new RegExp(`(?<![A-Za-z0-9_])${escaped}(?![A-Za-z0-9_])`, 'g'),
      placeholder,
    )
  }
  return result
}

/**
 * Returns true if any entity in the snapshot appears in the message text.
 *
 * Used to gate the per-message diff button — no point opening a diff for
 * a message that has nothing to mask.
 */
export function hasEntityMatches(content: string, snapshot: PrivacySnapshot): boolean {
  if (!content || !snapshot?.entities || snapshot.entities.length === 0) {
    return false
  }
  for (const entity of snapshot.entities) {
    const candidates = [entity.canonical, ...entity.aliases].filter(
      (value): value is string => Boolean(value),
    )
    for (const candidate of candidates) {
      if (matchesAtBoundary(content, candidate)) {
        return true
      }
    }
  }
  return false
}

/**
 * Boundary-aware substring check that mirrors the regex used by
 * `substituteEntities`. Avoids the bug where short numeric canonicals like
 * `"6"` would otherwise trigger this gate against any text containing "2026".
 */
export function matchesAtBoundary(content: string, needle: string): boolean {
  if (!needle) {
    return false
  }
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(?<![A-Za-z0-9_])${escaped}(?![A-Za-z0-9_])`).test(content)
}

/**
 * Tokenize a string into plain text + placeholder spans so we can render
 * `<<PERSON_1>>` as a styled chip inline. Returned array alternates between
 * `{ type: 'text' }` and `{ type: 'placeholder' }`.
 */
export type RemoteTextFragment =
  | { type: 'text'; value: string }
  | { type: 'placeholder'; value: string }

export function tokenizeRemoteText(text: string): RemoteTextFragment[] {
  if (!text) {
    return []
  }

  const fragments: RemoteTextFragment[] = []
  let lastIndex = 0
  PLACEHOLDER_PATTERN.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = PLACEHOLDER_PATTERN.exec(text)) !== null) {
    const start = match.index
    const end = start + match[0].length
    if (start > lastIndex) {
      fragments.push({ type: 'text', value: text.slice(lastIndex, start) })
    }
    fragments.push({ type: 'placeholder', value: match[0] })
    lastIndex = end
  }
  if (lastIndex < text.length) {
    fragments.push({ type: 'text', value: text.slice(lastIndex) })
  }
  return fragments
}
