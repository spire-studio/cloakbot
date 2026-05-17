import { FileText, Paperclip, Send, Upload, X } from 'lucide-react'
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  fileToAttachment,
  isDocumentMimeType,
  isImageMimeType,
} from '@/features/chat/lib/file-to-attachment'
import type { ChatAttachment } from '@/features/chat/types'
import { cn } from '@/lib/utils'
import { BRAND_NAME } from '@/shared/constants/brand'

type ComposerProps = {
  input: string
  onInputChange: (value: string) => void
  onSend: (attachments: ChatAttachment[]) => void
  isAwaitingAssistant: boolean
  layout?: 'landing' | 'conversation'
  className?: string
}

export function Composer({
  input,
  onInputChange,
  onSend,
  isAwaitingAssistant,
  layout = 'conversation',
  className,
}: ComposerProps) {
  const trimmedInput = input.trim()
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounterRef = useRef(0)

  const isSendDisabled =
    isAwaitingAssistant || (!trimmedInput && attachments.length === 0)

  const handleSend = useCallback(() => {
    if (isSendDisabled) {
      return
    }
    onSend(attachments)
    setAttachments([])
  }, [attachments, isSendDisabled, onSend])

  const addFiles = useCallback(async (fileList: FileList | File[]) => {
    const files = Array.from(fileList)
    const next: ChatAttachment[] = []
    for (const file of files) {
      const attachment = await fileToAttachment(file)
      if (attachment) {
        next.push(attachment)
      }
    }
    if (next.length === 0) {
      return
    }
    setAttachments((current) => [...current, ...next])
  }, [])

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (isImeComposition(event)) {
      return
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = event.clipboardData?.items
    if (!items) return
    const files: File[] = []
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i]
      if (item.kind !== 'file') {
        continue
      }
      if (!isImageMimeType(item.type) && !isDocumentMimeType(item.type)) {
        // Skip non-attachable file types — text/plain pastes that
        // arrive as `kind === "string"` still fall through to the
        // default paste behavior and land in the textarea normally.
        continue
      }
      const file = item.getAsFile()
      if (file) {
        files.push(file)
      }
    }
    if (files.length > 0) {
      event.preventDefault()
      void addFiles(files)
    }
  }

  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (files && files.length > 0) {
      void addFiles(files)
    }
    event.target.value = ''
  }

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer?.types?.includes('Files')) {
      return
    }
    event.preventDefault()
    dragCounterRef.current += 1
    setIsDragOver(true)
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer?.types?.includes('Files')) {
      return
    }
    event.preventDefault()
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragCounterRef.current -= 1
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setIsDragOver(false)
    }
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    dragCounterRef.current = 0
    setIsDragOver(false)
    const files = event.dataTransfer?.files
    if (files && files.length > 0) {
      void addFiles(files)
    }
  }

  const removeAttachmentAt = (index: number) => {
    setAttachments((current) => current.filter((_, i) => i !== index))
  }

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) {
      return
    }

    const minHeight = getTextareaMinHeight(textarea, layout)
    const maxHeight = getTextareaMaxHeight(textarea)
    textarea.style.height = '0px'
    const nextHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight))
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [input, layout])

  useEffect(() => {
    const handleResize = () => {
      const textarea = textareaRef.current
      if (!textarea) {
        return
      }

      const minHeight = getTextareaMinHeight(textarea, layout)
      const maxHeight = getTextareaMaxHeight(textarea)
      textarea.style.height = '0px'
      const nextHeight = Math.max(minHeight, Math.min(textarea.scrollHeight, maxHeight))
      textarea.style.height = `${nextHeight}px`
      textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
    }

    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [layout])

  return (
    <div
      className={cn(
        layout === 'landing' ? 'w-full' : 'shrink-0 px-4 pb-5 pt-4 lg:px-5',
        className,
      )}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="relative mx-auto max-w-[52rem]">
        <div
          className={cn(
            'relative w-full overflow-hidden rounded-[16px] border border-border bg-card shadow-[0_0_0_1px_var(--surface-outline)] transition-[box-shadow,border-color] duration-200 focus-within:border-border focus-within:shadow-[0_0_0_1px_var(--surface-outline-strong),0_20px_44px_var(--shadow-composer)]',
            isDragOver &&
              'border-[var(--privacy-medium-border)] shadow-[0_0_0_2px_var(--privacy-medium-border)]',
          )}
        >
          {attachments.length > 0 ? (
            <AttachmentTray attachments={attachments} onRemove={removeAttachmentAt} />
          ) : null}
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={`Ask ${BRAND_NAME} anything...`}
            className="m-0 min-h-0 w-full resize-none border-0 bg-transparent px-4 py-4 text-[15px] leading-[1.6] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:shadow-none"
            rows={layout === 'landing' ? 2 : 1}
          />
          <div className="flex items-center justify-between gap-2 px-3 py-2">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-[2.125rem] w-[2.125rem] shrink-0 rounded-lg text-muted-foreground hover:text-foreground"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Attach file"
              title="Attach image or document (PNG, JPG, WebP, GIF, TXT, MD)"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif,text/plain,text/markdown,.txt,.md,.markdown"
              multiple
              className="hidden"
              onChange={handleFileInputChange}
            />
            <Button
              size="icon"
              variant="default"
              className={cn(
                'h-[2.125rem] w-[2.125rem] shrink-0 rounded-lg transition-all duration-200',
                !isSendDisabled
                  ? 'opacity-100'
                  : 'border-secondary bg-secondary text-muted-foreground opacity-70 hover:bg-secondary',
              )}
              onClick={handleSend}
              disabled={isSendDisabled}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
          {isDragOver ? (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-[16px] bg-[var(--privacy-medium-bg)]/85 text-[13px] font-medium text-[var(--privacy-medium-text)]">
              <Upload className="mr-2 h-4 w-4" />
              Drop image or text document to attach
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

type AttachmentTrayProps = {
  attachments: ChatAttachment[]
  onRemove: (index: number) => void
}

function AttachmentTray({ attachments, onRemove }: AttachmentTrayProps) {
  return (
    <div className="flex flex-wrap items-stretch gap-2 border-b border-border/70 px-3 py-2.5">
      {attachments.map((attachment, index) => {
        const kind = attachment.kind ?? (attachment.mimeType.startsWith('image/') ? 'image' : 'document')
        const removeLabel = `Remove ${attachment.name ?? (kind === 'document' ? 'document' : 'image')}`
        if (kind === 'document') {
          return (
            <div
              key={`${attachment.name ?? 'document'}-${index}`}
              className="group relative flex h-14 min-w-[10rem] max-w-[16rem] items-center gap-2 rounded-lg border border-border bg-[var(--surface-subtle)] px-3"
              title={attachment.name ?? 'document'}
            >
              <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-[12px] font-medium text-foreground">
                  {attachment.name ?? 'document'}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {describeDocumentMime(attachment.mimeType)}
                </span>
              </div>
              <button
                type="button"
                onClick={() => onRemove(index)}
                className="absolute right-0 top-0 grid h-5 w-5 place-items-center rounded-bl-md bg-background/90 text-muted-foreground transition-colors hover:bg-destructive hover:text-destructive-foreground"
                aria-label={removeLabel}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )
        }
        return (
          <div
            key={`${attachment.name ?? 'image'}-${index}`}
            className="group relative h-14 w-14 overflow-hidden rounded-lg border border-border bg-[var(--surface-subtle)]"
          >
            <img
              src={attachment.dataUrl}
              alt={attachment.name ?? `attachment ${index + 1}`}
              className="h-full w-full object-cover"
            />
            <button
              type="button"
              onClick={() => onRemove(index)}
              className="absolute right-0 top-0 grid h-5 w-5 -translate-y-0 translate-x-0 place-items-center rounded-bl-md bg-background/90 text-muted-foreground transition-colors hover:bg-destructive hover:text-destructive-foreground"
              aria-label={removeLabel}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )
      })}
    </div>
  )
}

function describeDocumentMime(mimeType: string): string {
  if (mimeType === 'text/markdown') return 'Markdown'
  if (mimeType === 'text/plain') return 'Plain text'
  return mimeType
}

function isImeComposition(event: KeyboardEvent<HTMLTextAreaElement>) {
  return event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229
}

function getTextareaMinHeight(textarea: HTMLTextAreaElement, layout: ComposerProps['layout']) {
  const computedStyle = window.getComputedStyle(textarea)
  const lineHeight = Number.parseFloat(computedStyle.lineHeight) || 24
  const paddingTop = Number.parseFloat(computedStyle.paddingTop) || 0
  const paddingBottom = Number.parseFloat(computedStyle.paddingBottom) || 0
  const minRows = layout === 'landing' ? 1.33 : 1

  return lineHeight * minRows + paddingTop + paddingBottom
}

function getTextareaMaxHeight(textarea: HTMLTextAreaElement) {
  const computedStyle = window.getComputedStyle(textarea)
  const lineHeight = Number.parseFloat(computedStyle.lineHeight) || 24
  const paddingTop = Number.parseFloat(computedStyle.paddingTop) || 0
  const paddingBottom = Number.parseFloat(computedStyle.paddingBottom) || 0

  return Math.max(lineHeight + paddingTop + paddingBottom, lineHeight * 7 + paddingTop + paddingBottom)
}
