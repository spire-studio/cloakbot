import type { ChatAttachment } from '@/features/chat/types'

const ALLOWED_IMAGE_MIME_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
])

const MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024

/**
 * Convert a File/Blob from a drop/paste/file-picker event into the
 * `ChatAttachment` shape the WebSocket layer expects. Returns `null`
 * for unsupported mime types or oversized payloads — callers can show
 * a toast or just silently drop the attachment.
 */
export async function fileToAttachment(file: File): Promise<ChatAttachment | null> {
  if (!ALLOWED_IMAGE_MIME_TYPES.has(file.type)) {
    return null
  }
  if (file.size > MAX_ATTACHMENT_BYTES) {
    return null
  }
  const dataUrl = await readFileAsDataUrl(file)
  if (!dataUrl) {
    return null
  }
  return {
    mimeType: file.type,
    dataUrl,
    name: file.name || undefined,
  }
}

function readFileAsDataUrl(file: File): Promise<string | null> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      resolve(typeof result === 'string' ? result : null)
    }
    reader.onerror = () => resolve(null)
    reader.readAsDataURL(file)
  })
}

/** Quick MIME-type guard for paste/drop sources without reading the file. */
export function isImageMimeType(mimeType: string): boolean {
  return ALLOWED_IMAGE_MIME_TYPES.has(mimeType)
}
