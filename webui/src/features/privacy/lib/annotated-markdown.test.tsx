import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import { AnnotatedMarkdown } from './annotated-markdown'
import type { PrivacyAnnotation } from '@/features/privacy/types'

function createAnnotation(overrides: Partial<PrivacyAnnotation>): PrivacyAnnotation {
  return {
    placeholder: '<<PERSON_1>>',
    text: 'Alice',
    start: 0,
    end: 5,
    entity_type: 'person_name',
    severity: 'high',
    canonical: 'Alice',
    aliases: ['Alice'],
    value: 'Alice',
    ...overrides,
  }
}

function countHighlights(html: string) {
  return (html.match(/bg-secondary\/75/g) ?? []).length
}

describe('AnnotatedMarkdown', () => {
  it('renders annotated plain text spans with highlight styling', () => {
    const content = 'Hello Alice and welcome.'
    const annotations = [createAnnotation({ start: 6, end: 11 })]

    const html = renderToStaticMarkup(
      <AnnotatedMarkdown content={content} annotations={annotations} />,
    )

    expect(html).toContain('Hello ')
    expect(html).toContain('Alice')
    expect(countHighlights(html)).toBe(1)
    expect(html).toContain('<span class="rounded-[0.22rem] bg-secondary/75')
  })

  it('renders exact-match code nodes with annotation highlight styling', () => {
    const content = 'Use `Alice` here.'
    const annotations = [createAnnotation({ start: 5, end: 10 })]

    const html = renderToStaticMarkup(
      <AnnotatedMarkdown content={content} annotations={annotations} />,
    )

    expect(countHighlights(html)).toBe(1)
    expect(html).toContain('<code class="rounded-[0.22rem] bg-secondary/75')
    expect(html).toContain('>Alice</code>')
  })

  it('leaves partially overlapping code nodes unannotated', () => {
    const content = 'Use `Alice and Bob` here.'
    const annotations = [createAnnotation({ start: 5, end: 10 })]

    const html = renderToStaticMarkup(
      <AnnotatedMarkdown content={content} annotations={annotations} />,
    )

    expect(countHighlights(html)).toBe(0)
    expect(html).toContain('<code>Alice and Bob</code>')
  })
})
