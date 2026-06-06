import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AnnotatedMarkdown } from '@/overlays/privacy/lib/annotated-markdown'
import type { PrivacyAnnotation } from '@/overlays/privacy/types'

// "Your name is Alice Chen." — "Alice Chen" occupies offsets [13, 23) of the
// restored display string (the same string the backend annotations index).
const aliceAnnotation: PrivacyAnnotation = {
  annotation_type: 'entity',
  placeholder: '<<PERSON_1>>',
  text: 'Alice Chen',
  start: 13,
  end: 23,
  entity_type: 'person',
  severity: 'high',
  canonical: 'Alice Chen',
  aliases: ['Alice Chen'],
  value: null,
}

describe('AnnotatedMarkdown', () => {
  it('wraps a restored entity span in a hover-highlight over the real value', () => {
    render(<AnnotatedMarkdown content="Your name is Alice Chen." annotations={[aliceAnnotation]} />)
    const span = screen.getByText('Alice Chen')
    expect(span.tagName).toBe('SPAN')
    // PRIVACY_HIGHLIGHT_CLASS_NAME is applied -> visible highlight.
    expect(span).toHaveClass('border-sky-300/70')
    // Wrapped in a Radix tooltip trigger -> hoverable for the placeholder<->value detail.
    expect(span).toHaveAttribute('data-state')
  })

  it('renders content unchanged when no entities were restored', () => {
    render(<AnnotatedMarkdown content="No private data here." annotations={[]} />)
    expect(screen.getByText('No private data here.')).toBeInTheDocument()
    // No highlighted/hoverable spans when nothing was restored.
    expect(document.querySelector('[data-state]')).toBeNull()
  })
})
