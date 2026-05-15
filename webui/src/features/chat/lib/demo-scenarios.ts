import { Briefcase, GraduationCap, Receipt, Stethoscope, type LucideIcon } from 'lucide-react'

export type DemoScenarioId = 'medical' | 'hr' | 'travel' | 'tutoring'

export type DemoScenario = {
  id: DemoScenarioId
  title: string
  blurb: string
  icon: LucideIcon
  /** Optional thumbnail path under /public/demo/. Falls back to icon when missing. */
  thumbnail?: string
  /** Human-readable attachment label shown as a chip on the card. */
  attachmentLabel: string
  /** The prompt actually sent to the model. */
  prompt: string
}

/**
 * Pre-built scenarios for the one-click demo launcher.
 *
 * Each prompt is rich in PII so the audience can see Cloakbot's placeholders
 * light up in the privacy panel within a second of clicking the card.
 *
 * Drop matching PNGs in /webui/public/demo/{id}.png to enable thumbnail
 * previews — the cards degrade gracefully to the lucide icon if absent.
 */
export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: 'medical',
    title: 'Medical consultation',
    blurb: 'Ask the model to summarize a patient follow-up that includes full name, doctor, and medication.',
    icon: Stethoscope,
    thumbnail: '/demo/medical.png',
    attachmentLabel: 'patient-note.png',
    prompt:
      "Hi, I'm helping my mother, Margaret O'Sullivan (DOB 1948-03-12), follow up on her cardiology appointment with Dr. Henry Whitaker at BlueCross PPO. She was prescribed Apixaban 5mg twice daily and Atorvastatin 40mg nightly for atrial fibrillation and high cholesterol. Her phone is +1 (415) 555-2088 and she lives at 245 Morgan Stream, Heidiville, ID 05939. Can you draft a short note to her primary care team summarizing the new regimen and asking about side effects?",
  },
  {
    id: 'hr',
    title: 'HR resume screening',
    blurb: "Hand the model a candidate's resume snippet so it can shortlist without seeing real identity.",
    icon: Briefcase,
    thumbnail: '/demo/hr.png',
    attachmentLabel: 'candidate-resume.png',
    prompt:
      "I'm reviewing this candidate for our senior platform role:\n\nName: Jonathan S. Pereira\nEmail: jpereira.work@gmail.com\nPhone: +1 (646) 555-0144\nLinkedIn: linkedin.com/in/jpereira-eng\nCurrent: Senior SRE at Acme Corp ($178,000 base)\nPrevious: Staff Engineer at Hall PLC ($162,000 base)\nLocation: 88 Bedford Ave, Brooklyn, NY 11211\nSSN (last 4): 4827\n\nCan you draft three screening questions and a polite first-round email? Keep it under 120 words.",
  },
  {
    id: 'travel',
    title: 'Cross-border expense',
    blurb: 'Reconcile a multi-currency invoice with card numbers, addresses, and vendor names redacted.',
    icon: Receipt,
    thumbnail: '/demo/travel.png',
    attachmentLabel: 'invoice-amex.png',
    prompt:
      "Help me file this Q1 expense. The invoice is from Taylor-Simmons Consulting (INV-2024-A8K3, dated 2026-04-22). Total was €4,820.50 charged to my corporate Amex ending 7142. I'm Laura Chen at 1600 Pennsylvania Ave NW, Washington, DC 20500. Reimbursement should land in my Chase account 0000-1729. Can you write a one-paragraph justification and tag the right GL code (consulting vs. travel)?",
  },
  {
    id: 'tutoring',
    title: 'Student tutoring session',
    blurb: "Plan a tutoring session that mentions the student's name, parent contact, and home address.",
    icon: GraduationCap,
    thumbnail: '/demo/tutoring.png',
    attachmentLabel: 'progress-report.png',
    prompt:
      "I'm tutoring Emily Park (8th grade) on algebra. Her mom Sarah Park (sarah.park.tutor@outlook.com, +1 (212) 555-0177) wants a Tuesday/Thursday plan after school. Their address is Apt 5B, 245 Morgan Stream, Heidiville, ID 05939. Emily struggles with quadratics but is strong on linear systems. Draft a 4-week study plan and a friendly recap email for Sarah summarizing today's session.",
  },
]
