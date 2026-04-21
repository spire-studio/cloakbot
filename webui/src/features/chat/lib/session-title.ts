export function buildSessionTitle(firstUserMessage: string): string {
  const normalized = firstUserMessage.trim().replace(/\s+/g, ' ')

  if (normalized.length === 0) {
    return 'New chat'
  }

  if (normalized.length > 48) {
    return `${normalized.slice(0, 47)}…`
  }

  return normalized
}
