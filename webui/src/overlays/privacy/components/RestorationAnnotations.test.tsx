import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RestorationAnnotations } from '@/overlays/privacy/components/RestorationAnnotations'
import type { PrivacyAnnotation } from '@/overlays/privacy/types'

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

describe('RestorationAnnotations Diff toggle', () => {
  it('defaults to Local (real value) and toggles to Remote (placeholder)', () => {
    render(<RestorationAnnotations content="Your name is Alice Chen." annotations={[aliceAnnotation]} />)
    // Local: the locally-restored real value.
    expect(screen.getByText('Alice Chen')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Remote' }))
    // Remote: the exact placeholder the model received.
    expect(screen.getByText('<<PERSON_1>>')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Local' }))
    expect(screen.getByText('Alice Chen')).toBeInTheDocument()
  })

  it('renders plainly with no toggle when there are no annotations', () => {
    render(<RestorationAnnotations content="Nothing private here." annotations={[]} />)
    expect(screen.getByText('Nothing private here.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remote' })).toBeNull()
  })
})
