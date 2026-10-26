// Sprint 3 (1.16.0): the guidance a Manager writes for each induction, as the lines the Induction page shows.
import type { Requirement } from '../../api/types/index.ts'

export const GUIDE_LABELS = {
  how_to_complete: 'How to complete it',
  accepted_evidence: 'What to upload',
  reviewer: 'Who checks it',
  contact: 'Who to ask',
} as const

/** The filled-in guidance lines, in a fixed order (empty ones are left out). */
export function guideItems(requirement: Requirement): { label: string; text: string }[] {
  return (Object.keys(GUIDE_LABELS) as (keyof typeof GUIDE_LABELS)[])
    .map((key) => ({ label: GUIDE_LABELS[key], text: (requirement[key] ?? '').trim() }))
    .filter((item) => item.text)
}
