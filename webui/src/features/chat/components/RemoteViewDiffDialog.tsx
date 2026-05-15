import { ArrowRight, Eye, EyeOff, Shield } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Chip } from '@/components/ui/chip'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useRemoteView } from '@/features/chat/context/RemoteViewContext'
import {
  matchesAtBoundary,
  substituteEntities,
  tokenizeRemoteText,
} from '@/features/chat/lib/remote-view-substitute'
import type { ChatMessage } from '@/features/chat/types'
import type { PrivacySnapshot } from '@/features/privacy/types'

type RemoteViewDiffDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  message: ChatMessage | null
  snapshot: PrivacySnapshot
}

const DIFF_HIGHLIGHT_CLASS =
  'rounded-[0.32rem] border border-[var(--privacy-highlight-border)] bg-[var(--privacy-highlight)] px-[0.32rem] py-[0.06rem] text-inherit'

const PLACEHOLDER_CHIP_CLASS =
  'inline-flex items-center rounded-md border border-[var(--privacy-medium-border)] bg-[var(--privacy-medium-bg)] px-1.5 py-[0.05rem] font-mono text-[0.78em] text-[var(--privacy-medium-text)]'

export function RemoteViewDiffDialog({
  open,
  onOpenChange,
  message,
  snapshot,
}: RemoteViewDiffDialogProps) {
  const { isRemote, setMode } = useRemoteView()

  if (!message) {
    return null
  }

  const remoteText = substituteEntities(message.content, snapshot.entities)
  const matchedEntities = snapshot.entities.filter(
    (entity) =>
      (entity.canonical && matchesAtBoundary(message.content, entity.canonical)) ||
      entity.aliases.some((alias) => alias && matchesAtBoundary(message.content, alias)),
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-muted-foreground" />
            Local vs. Remote view
          </DialogTitle>
          <DialogDescription>
            Side-by-side comparison of your original message and the sanitized payload the cloud
            model received.
          </DialogDescription>
        </DialogHeader>

        {message.attachments && message.attachments.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <DiffColumn
              label="You uploaded"
              tone="local"
              footer={`${message.attachments.length} image${message.attachments.length === 1 ? '' : 's'}`}
            >
              <AttachmentColumn
                attachments={message.attachments}
                kind="original"
                results={message.attachmentResults}
              />
            </DiffColumn>
            <DiffColumn
              label="Remote saw"
              tone="remote"
              footer={`${(message.attachmentResults ?? []).filter((r) => r.status === 'redacted').length} redacted · ${(message.attachmentResults ?? []).filter((r) => r.status === 'omitted').length} omitted`}
            >
              <AttachmentColumn
                attachments={message.attachments}
                kind="redacted"
                results={message.attachmentResults}
              />
            </DiffColumn>
          </div>
        ) : null}

        {message.content ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <DiffColumn
              label="You typed"
              tone="local"
              footer={`${message.content.length} chars · ${matchedEntities.length} entities matched`}
            >
              <HighlightedOriginal content={message.content} matched={matchedEntities} />
            </DiffColumn>
            <DiffColumn
              label="Remote saw"
              tone="remote"
              footer={`${remoteText.length} chars · ${matchedEntities.length} placeholders`}
            >
              <PlaceholderText text={remoteText} />
            </DiffColumn>
          </div>
        ) : null}

        {matchedEntities.length > 0 ? (
          <div className="rounded-xl border border-border bg-[var(--surface-subtle)] px-3 py-2.5">
            <div className="mb-1.5 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
              Entities replaced
            </div>
            <div className="flex flex-wrap gap-1.5">
              {matchedEntities.map((entity) => (
                <Chip key={entity.placeholder} variant="fill" className="gap-1">
                  <span className="font-mono">{entity.placeholder}</span>
                  <ArrowRight className="h-2.5 w-2.5 opacity-70" />
                  <span className="text-foreground">{entity.canonical}</span>
                </Chip>
              ))}
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 rounded-lg px-3"
            onClick={() => setMode(isRemote ? 'local' : 'remote')}
          >
            {isRemote ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            <span>
              {isRemote ? 'Show all messages locally' : 'Apply Remote view to all messages'}
            </span>
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-8 rounded-lg px-3"
            onClick={() => onOpenChange(false)}
          >
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type DiffColumnProps = {
  label: string
  tone: 'local' | 'remote'
  footer: string
  children: ReactNode
}

function DiffColumn({ label, tone, footer, children }: DiffColumnProps) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
      <header className="flex items-center justify-between gap-2 border-b border-border/70 px-3 py-2">
        <div className="flex items-center gap-2">
          {tone === 'local' ? (
            <Eye className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <EyeOff className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <span className="text-[12px] font-medium text-foreground">{label}</span>
        </div>
        <Chip>{tone === 'local' ? 'plaintext' : 'sanitized'}</Chip>
      </header>
      <ScrollArea className="max-h-[44vh] min-h-[8rem] flex-1">
        <pre className="whitespace-pre-wrap break-words px-3 py-3 font-sans text-[13px] leading-[1.65] text-foreground">
          {children}
        </pre>
      </ScrollArea>
      <footer className="border-t border-border/70 px-3 py-1.5 text-[11px] text-muted-foreground">
        {footer}
      </footer>
    </section>
  )
}

function HighlightedOriginal({
  content,
  matched,
}: {
  content: string
  matched: ReadonlyArray<{ canonical: string; aliases: string[]; placeholder: string }>
}) {
  if (matched.length === 0) {
    return <span>{content}</span>
  }

  type Hit = { start: number; end: number }
  const hits: Hit[] = []
  for (const entity of matched) {
    const needles = [entity.canonical, ...entity.aliases]
      .filter((value): value is string => Boolean(value))
      .sort((left, right) => right.length - left.length)
    for (const needle of needles) {
      const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      // ASCII word-boundary lookbehind/lookahead — mirrors `substituteEntities`
      // so short numeric needles ("6") don't highlight digits inside larger
      // numbers like "2026".
      const regex = new RegExp(`(?<![A-Za-z0-9_])${escaped}(?![A-Za-z0-9_])`, 'g')
      let match: RegExpExecArray | null
      while ((match = regex.exec(content)) !== null) {
        const start = match.index
        const end = start + needle.length
        if (!hits.some((hit) => hit.start < end && hit.end > start)) {
          hits.push({ start, end })
        }
      }
    }
  }

  if (hits.length === 0) {
    return <span>{content}</span>
  }

  hits.sort((left, right) => left.start - right.start)

  const nodes: ReactNode[] = []
  let cursor = 0
  hits.forEach((hit, index) => {
    if (hit.start > cursor) {
      nodes.push(<Fragment key={`text-${index}`}>{content.slice(cursor, hit.start)}</Fragment>)
    }
    nodes.push(
      <span key={`hit-${index}`} className={DIFF_HIGHLIGHT_CLASS}>
        {content.slice(hit.start, hit.end)}
      </span>,
    )
    cursor = hit.end
  })
  if (cursor < content.length) {
    nodes.push(<Fragment key="text-tail">{content.slice(cursor)}</Fragment>)
  }
  return <>{nodes}</>
}

function AttachmentColumn({
  attachments,
  kind,
  results,
}: {
  attachments: NonNullable<ChatMessage['attachments']>
  kind: 'original' | 'redacted'
  results: ChatMessage['attachmentResults']
}) {
  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      {attachments.map((attachment, index) => {
        const result = results?.[index]
        if (kind === 'redacted' && (!result || !result.redactedDataUrl)) {
          return (
            <div
              key={`redacted-omitted-${index}`}
              className="rounded-lg border border-dashed border-border bg-[var(--surface-subtle)] px-3 py-4 text-center text-[11px] leading-[1.5] text-muted-foreground"
            >
              {result?.status === 'omitted'
                ? `Omitted from remote payload — ${result.reason ?? 'fail-closed redaction'}.`
                : 'Awaiting redaction…'}
            </div>
          )
        }
        const src = kind === 'original' ? attachment.dataUrl : result!.redactedDataUrl!
        const labels = result?.redaction?.labels ?? []
        const boxes = result?.redaction?.redactionBoxes ?? 0
        return (
          <figure
            key={`${kind}-${index}`}
            className="overflow-hidden rounded-lg border border-border bg-card"
          >
            <img
              src={src}
              alt={
                kind === 'original'
                  ? attachment.name ?? `original ${index + 1}`
                  : `redacted ${index + 1}`
              }
              className="w-full"
            />
            {kind === 'redacted' && (labels.length > 0 || boxes > 0) ? (
              <figcaption className="border-t border-border/70 px-3 py-2 text-[11px] text-muted-foreground">
                {boxes} redaction box{boxes === 1 ? '' : 'es'}
                {labels.length > 0 ? ` · ${labels.join(', ')}` : ''}
              </figcaption>
            ) : null}
          </figure>
        )
      })}
    </div>
  )
}

function PlaceholderText({ text }: { text: string }) {
  const fragments = tokenizeRemoteText(text)
  if (fragments.length === 0) {
    return <span>{text}</span>
  }
  return (
    <>
      {fragments.map((fragment, index) =>
        fragment.type === 'placeholder' ? (
          <span key={`p-${index}`} className={PLACEHOLDER_CHIP_CLASS}>
            {fragment.value}
          </span>
        ) : (
          <Fragment key={`t-${index}`}>{fragment.value}</Fragment>
        ),
      )}
    </>
  )
}
