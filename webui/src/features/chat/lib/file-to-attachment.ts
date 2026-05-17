import type { ChatAttachment } from '@/features/chat/types'

const ALLOWED_IMAGE_MIME_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
])

const ALLOWED_DOCUMENT_MIME_TYPES = new Set([
  'text/plain',
  'text/markdown',
])

const MAX_IMAGE_BYTES = 12 * 1024 * 1024
// Documents go through the chunker-backed PII detector — keep the
// upper bound conservative (≈64KB of UTF-8 text). Above this the
// backend rejects the upload anyway, and chunking a 1MB paste would
// dominate latency long before it produced a useful signal.
const MAX_DOCUMENT_BYTES = 64 * 1024

const MARKDOWN_EXTENSIONS = ['.md', '.markdown']

/** Some browsers leave .md uploads with an empty MIME — fall back on extension. */
function resolveDocumentMimeType(file: File): string | null {
  if (ALLOWED_DOCUMENT_MIME_TYPES.has(file.type)) {
    return file.type
  }
  const name = file.name?.toLowerCase() || ''
  if (MARKDOWN_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return 'text/markdown'
  }
  if (name.endsWith('.txt') && (!file.type || file.type === 'text/plain')) {
    return 'text/plain'
  }
  return null
}

/**
 * Convert a File/Blob from a drop/paste/file-picker event into the
 * `ChatAttachment` shape the WebSocket layer expects. Returns `null`
 * for unsupported mime types or oversized payloads — callers can show
 * a toast or just silently drop the attachment.
 *
 * Routing rule: image MIMEs → visual privacy pipeline (image kind);
 * text/plain or text/markdown → chunker-backed document pipeline
 * (document kind). Other types are rejected here so the WS layer
 * never sees an upload the backend doesn't know how to handle.
 */
export async function fileToAttachment(file: File): Promise<ChatAttachment | null> {
  if (ALLOWED_IMAGE_MIME_TYPES.has(file.type)) {
    if (file.size > MAX_IMAGE_BYTES) {
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
      kind: 'image',
    }
  }

  const documentMime = resolveDocumentMimeType(file)
  if (documentMime) {
    if (file.size > MAX_DOCUMENT_BYTES) {
      return null
    }
    const dataUrl = await readFileAsDataUrl(file)
    if (!dataUrl) {
      return null
    }
    // ``data:text/plain;base64,…`` is what the privacy pipeline's
    // _DOCUMENT_DATA_URL_PATTERN expects. FileReader returns the
    // correct shape on its own as long as the file's MIME is set, but
    // we re-wrap when the browser handed us an empty MIME and we
    // inferred it from the extension.
    const normalizedDataUrl = dataUrl.startsWith(`data:${documentMime};`)
      ? dataUrl
      : dataUrl.replace(/^data:[^;]*;/, `data:${documentMime};`)
    return {
      mimeType: documentMime,
      dataUrl: normalizedDataUrl,
      name: file.name || undefined,
      kind: 'document',
    }
  }

  return null
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

/** Quick MIME-type guard for paste/drop sources without reading the file. */
export function isDocumentMimeType(mimeType: string): boolean {
  return ALLOWED_DOCUMENT_MIME_TYPES.has(mimeType)
}
