import { Link } from 'react-router'
import { CapIcon, CheckIcon, AlertIcon, ClockIcon } from '../booking/icons'
import type { Qualification, Requirement, Resource } from '../../api/types/index.ts'
import { describeInduction, unlocksText } from './status'
import { InductionGuide } from './InductionGuide' // Sprint 3 (1.16.0)

interface Props {
  requirement: Requirement
  latest?: Qualification
  resources: Resource[]
  /** Dashboard: the whole row links to the induction page for this requirement. */
  linkTo?: string
  /** Induction page: open the upload form for this requirement. */
  onUpload?: (requirementId: string) => void
  /** Induction page: show the latest submission. */
  onView?: (submission: Qualification) => void
  showDescription?: boolean
  /** Name of a prerequisite that is not verified and current (e.g. General for Advanced). */
  blockedBy?: string | null
}

type Step = { label: string; state: 'done' | 'current' | 'failed' | 'todo' }

function steps(status: string): Step[] {
  switch (status) {
    case 'PENDING': return [{ label: 'Submitted', state: 'done' }, { label: 'Under review', state: 'current' }, { label: 'Verified', state: 'todo' }]
    case 'VERIFIED': return [{ label: 'Submitted', state: 'done' }, { label: 'Reviewed', state: 'done' }, { label: 'Verified', state: 'done' }]
    case 'REJECTED': return [{ label: 'Submitted', state: 'done' }, { label: 'Reviewed', state: 'done' }, { label: 'Rejected', state: 'failed' }]
    case 'EXPIRED': return [{ label: 'Submitted', state: 'done' }, { label: 'Verified', state: 'done' }, { label: 'Expired', state: 'failed' }]
    default: return []
  }
}

export function InductionRow({ requirement, latest, resources, linkTo, onUpload, onView, showDescription, blockedBy = null }: Props) {
  const view = describeInduction(latest, blockedBy)
  const unlocks = unlocksText(requirement.id, resources)
  const icon = view.tone === 'green' ? <CheckIcon /> : view.tone === 'amber' ? <ClockIcon /> : view.tone === 'red' ? <AlertIcon /> : <CapIcon />
  const actionLabel = view.action === 'reupload' ? 'Re-upload' : 'Upload'

  const action = view.action && (onUpload
    ? <button type="button" className="ui-btn ui-btn-primary ui-btn-sm" onClick={(e) => { e.preventDefault(); onUpload(requirement.id) }}>{actionLabel}</button>
    : <span className="ui-btn ui-btn-primary ui-btn-sm">{actionLabel}</span>)
  const viewButton = view.status === 'PENDING' && latest && (onView
    ? <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={(e) => { e.preventDefault(); onView(latest) }}>View submission</button>
    : <span className="ui-btn ui-btn-ghost ui-btn-sm">View submission</span>)

  const body = (
    <>
      <span className={`ind-icon is-${view.tone}`} aria-hidden="true">{icon}</span>
      <div className="ind-main">
        <div className="ind-title">
          <h3>{requirement.name}</h3>
          <span className={`ui-pill is-${view.tone}`}>{view.label}</span>
        </div>
        {showDescription && requirement.description && <p className="ind-desc">{requirement.description}</p>}
        <p className="ind-detail">{view.detail}</p>
        {unlocks && <p className="ind-unlocks">Lets you book: {unlocks}</p>}
        {view.status !== 'NOT_SUBMITTED' && (
          <ol className="ind-steps" aria-label="Progress">
            {steps(view.status).map((step) => <li key={step.label} className={`is-${step.state}`}>{step.label}</li>)}
          </ol>
        )}
        {/* Sprint 3 (1.16.0): guidance for people who do not have it yet (Induction page only). */}
        {showDescription && <InductionGuide requirement={requirement} open={view.status !== 'VERIFIED'} />}
      </div>
      {(action || viewButton) && <div className="ind-actions">{viewButton}{action}</div>}
    </>
  )

  return linkTo
    ? <Link className="ind-row is-link" to={linkTo} aria-label={`${requirement.name}: ${view.label}. ${view.detail}`}>{body}</Link>
    : <div className="ind-row">{body}</div>
}
