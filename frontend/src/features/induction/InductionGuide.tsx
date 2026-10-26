// Sprint 3 (1.16.0): "How to get this induction" under each induction on the Induction & Training page.
import { ContactLink } from '../contact/LabContact'
import type { Requirement } from '../../api/types/index.ts'
import { guideItems } from './guide'

/**
 * What a person without the induction should do next, as written by a Manager on Lab setup. Open by default until
 * the induction is verified. Without any guidance it says so and offers the lab's email (when there is one).
 */
export function InductionGuide({ requirement, open }: { requirement: Requirement; open: boolean }) {
  const items = guideItems(requirement)
  return (
    <details className="ind-guide" open={open}>
      <summary>How to get this induction</summary>
      {items.length > 0 ? (
        <dl>{items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.text}</dd></div>)}</dl>
      ) : (
        <p className="bk-muted">The lab has not written instructions for this induction yet.</p>
      )}
      <ContactLink label="Ask the lab about this induction" subject={`Induction: ${requirement.name}`} />
    </details>
  )
}
