import { cloneElement, type ComponentPropsWithoutRef, type ReactElement, type ReactNode } from 'react'
import ReactMarkdown, { type ExtraProps } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { Chip } from '@/components/ui/chip'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

import type { PrivacyAnnotation } from '@/features/privacy/types'

type MarkdownPoint = {
  offset?: number
}

type MarkdownPosition = {
  start?: MarkdownPoint
  end?: MarkdownPoint
}

type MarkdownTextNode = {
  type: 'text'
  value: string
  position?: MarkdownPosition
}

type MarkdownElementNode = {
  type: 'element'
  tagName: string
  children?: MarkdownNode[]
  properties?: Record<string, unknown> & {
    dataPrivacyIndex?: string | number
  }
  position?: MarkdownPosition
}

type MarkdownRootNode = {
  type: 'root'
  children?: MarkdownNode[]
  position?: MarkdownPosition
}

type MarkdownNode = MarkdownRootNode | MarkdownElementNode | MarkdownTextNode

type MarkdownSpanProps = ComponentPropsWithoutRef<'span'> & ExtraProps

type MarkdownCodeProps = ComponentPropsWithoutRef<'code'> & ExtraProps

const PRIVACY_HIGHLIGHT_CLASS_NAME =
  'rounded-[0.32rem] border border-[var(--privacy-highlight-border)] bg-[var(--privacy-highlight)] px-[0.38rem] py-[0.12rem] text-inherit transition-colors hover:bg-[var(--privacy-highlight-hover)]'

function formatEntityLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function privacySeverityClasses(severity: PrivacyAnnotation['severity']) {
  if (severity === 'high') {
    return 'border-[var(--privacy-high-border)] bg-[var(--privacy-high-bg)] text-[var(--privacy-high-text)]'
  }
  if (severity === 'medium') {
    return 'border-[var(--privacy-medium-border)] bg-[var(--privacy-medium-bg)] text-[var(--privacy-medium-text)]'
  }
  return 'border-[var(--privacy-low-border)] bg-[var(--privacy-low-bg)] text-[var(--privacy-low-text)]'
}

function isTextNode(node: MarkdownNode): node is MarkdownTextNode {
  return node.type === 'text'
}

function isElementNode(node: MarkdownNode): node is MarkdownElementNode {
  return node.type === 'element'
}

function hasChildren(node: MarkdownNode): node is MarkdownRootNode | MarkdownElementNode {
  return 'children' in node && Array.isArray(node.children)
}

function getNodeOffsets(node: { position?: MarkdownPosition } | undefined) {
  const start = node?.position?.start?.offset
  const end = node?.position?.end?.offset

  if (typeof start !== 'number' || typeof end !== 'number' || start >= end) {
    return null
  }

  return { start, end }
}

function getAnnotationFromIndex(
  node: MarkdownElementNode | undefined,
  annotations: PrivacyAnnotation[],
) {
  const rawIndex = node?.properties?.dataPrivacyIndex
  const annotationIndex =
    typeof rawIndex === 'string' ? Number(rawIndex) : typeof rawIndex === 'number' ? rawIndex : undefined

  if (annotationIndex === undefined || !Number.isInteger(annotationIndex)) {
    return undefined
  }

  return annotations[annotationIndex]
}

function getExactCodeAnnotation(
  node: MarkdownElementNode | undefined,
  codeText: string,
  annotations: PrivacyAnnotation[],
) {
  const offsets = getNodeOffsets(node)

  if (!offsets) {
    const exactTextMatches = annotations.filter((annotation) => annotation.text === codeText)
    return exactTextMatches.length === 1 ? exactTextMatches[0] : undefined
  }

  const overlapping = annotations.filter(
    (annotation) => annotation.start < offsets.end && annotation.end > offsets.start,
  )

  if (overlapping.length !== 1) {
    return undefined
  }

  const [annotation] = overlapping
  return annotation.text === codeText ? annotation : undefined
}

function AnnotationTooltipBody({ annotation }: { annotation: PrivacyAnnotation }) {
  const extraAliases = annotation.aliases.filter((alias) => alias !== annotation.canonical)
  const isLocalComputation = annotation.annotation_type === 'local_computation'

  if (isLocalComputation) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center gap-2">
          <div className="text-[11px] tracking-[0.08em] text-muted-foreground">
            Local Computation
          </div>
          <Chip className={privacySeverityClasses(annotation.severity)}>{annotation.severity}</Chip>
        </div>
        {annotation.formula ? (
          <div className="font-mono text-xs leading-6 text-foreground">
            {annotation.formula} = {annotation.text}
          </div>
        ) : (
          <div className="text-sm font-medium text-foreground">{annotation.text}</div>
        )}
        <div className="text-xs text-muted-foreground">
          Computed locally on-device after the remote model returned the structure.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <div className="text-[11px] tracking-[0.08em] text-muted-foreground">
          Privacy-Protected Entity
        </div>
        <Chip className={privacySeverityClasses(annotation.severity)}>{annotation.severity}</Chip>
      </div>
      <div className="text-sm font-medium text-foreground">{annotation.canonical}</div>
      <div className="text-xs text-muted-foreground">
        {formatEntityLabel(annotation.entity_type)} · {annotation.placeholder}
      </div>
      {extraAliases.length > 0 && (
        <div className="text-xs text-muted-foreground">Aliases: {extraAliases.join(', ')}</div>
      )}
      {annotation.value !== null && annotation.value !== undefined && (
        <div className="text-xs text-muted-foreground">Normalized value: {String(annotation.value)}</div>
      )}
    </div>
  )
}

function renderAnnotatedElement(
  element: ReactElement<{ className?: string }>,
  annotation: PrivacyAnnotation | undefined,
) {
  if (!annotation) {
    return element
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {cloneElement(element, {
          className: cn(PRIVACY_HIGHLIGHT_CLASS_NAME, element.props.className),
        })}
      </TooltipTrigger>
      <TooltipContent>
        <AnnotationTooltipBody annotation={annotation} />
      </TooltipContent>
    </Tooltip>
  )
}

function splitTextNodeByPrivacyAnnotations(
  node: MarkdownTextNode,
  annotations: PrivacyAnnotation[],
): MarkdownNode[] | null {
  const offsets = getNodeOffsets(node)
  if (!offsets) {
    return null
  }

  const overlapping = annotations.filter(
    (annotation) => annotation.start < offsets.end && annotation.end > offsets.start,
  )
  if (overlapping.length === 0) {
    return null
  }

  const fragments: MarkdownNode[] = []
  let cursor = offsets.start

  for (const [annotationIndex, annotation] of annotations.entries()) {
    if (annotation.start >= offsets.end || annotation.end <= offsets.start) {
      continue
    }

    let segmentStart = Math.max(annotation.start, offsets.start)
    let segmentEnd = Math.min(annotation.end, offsets.end)
    let localStart = segmentStart - offsets.start
    let localEnd = segmentEnd - offsets.start
    const currentSlice = node.value.slice(localStart, localEnd)
    if (currentSlice !== annotation.text) {
      const snappedStart = node.value.indexOf(annotation.text, Math.max(0, localStart - 1))
      if (snappedStart >= 0 && snappedStart <= localStart + 1) {
        localStart = snappedStart
        localEnd = snappedStart + annotation.text.length
        segmentStart = offsets.start + localStart
        segmentEnd = offsets.start + localEnd
      }
    }

    const alignedSlice = node.value.slice(localStart, localEnd)
    const isPartialBoundaryOverlap = annotation.start < offsets.start || annotation.end > offsets.end
    if (alignedSlice !== annotation.text && isPartialBoundaryOverlap) {
      continue
    }

    if (segmentStart > cursor) {
      fragments.push({
        type: 'text',
        value: node.value.slice(cursor - offsets.start, segmentStart - offsets.start),
      })
    }

    fragments.push({
      type: 'element',
      tagName: 'span',
      properties: {
        dataPrivacyIndex: String(annotationIndex),
      },
      children: [
        {
          type: 'text',
          value: node.value.slice(localStart, localEnd),
        },
      ],
    })
    cursor = segmentEnd
  }

  if (cursor < offsets.end) {
    fragments.push({
      type: 'text',
      value: node.value.slice(cursor - offsets.start),
    })
  }

  return fragments
}

function annotateMarkdownTree(node: MarkdownRootNode | MarkdownElementNode, annotations: PrivacyAnnotation[], insideCode = false) {
  if (!Array.isArray(node.children)) {
    return
  }

  const nextInsideCode =
    insideCode || (isElementNode(node) && (node.tagName === 'code' || node.tagName === 'pre'))

  for (let index = node.children.length - 1; index >= 0; index -= 1) {
    const child = node.children[index]
    if (!nextInsideCode && isTextNode(child)) {
      const fragments = splitTextNodeByPrivacyAnnotations(child, annotations)
      if (fragments) {
        node.children.splice(index, 1, ...fragments)
        continue
      }
    }

    if (hasChildren(child)) {
      annotateMarkdownTree(child, annotations, nextInsideCode)
    }
  }
}

export function AnnotatedMarkdown({
  content,
  annotations,
  invert,
}: {
  content: string
  annotations: PrivacyAnnotation[]
  invert?: boolean
}) {
  const sortedAnnotations = [...annotations].sort((left, right) => left.start - right.start)
  const rehypePrivacyPlugin = () => {
    return (tree: MarkdownRootNode) => {
      annotateMarkdownTree(tree, sortedAnnotations)
    }
  }

  return (
    <TooltipProvider delayDuration={120}>
      <div className={cn('prose max-w-none break-words text-current', invert ? 'prose-invert' : 'dark:prose-invert')}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypePrivacyPlugin]}
          components={{
            span({ node, className, children, ...props }: MarkdownSpanProps) {
              const annotation = getAnnotationFromIndex(
                isElementNode(node as MarkdownNode) ? (node as MarkdownElementNode) : undefined,
                sortedAnnotations,
              )

              return renderAnnotatedElement(
                <span className={className} {...props}>
                  {children}
                </span>,
                annotation,
              )
            },
            code({ node, className, children, ...props }: MarkdownCodeProps) {
              const codeText = String(children).replace(/\n$/, '')
              const annotation = getExactCodeAnnotation(
                isElementNode(node as MarkdownNode) ? (node as MarkdownElementNode) : undefined,
                codeText,
                sortedAnnotations,
              )

              return renderAnnotatedElement(
                <code className={className} {...props}>
                  {children as ReactNode}
                </code>,
                annotation,
              )
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </TooltipProvider>
  )
}
