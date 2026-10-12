import { AlertIcon, CheckIcon, PinIcon } from './icons'
import type { Resource } from './types'

export type InductionState = 'VERIFIED' | 'PENDING' | 'NOT_SUBMITTED' | 'REJECTED' | 'EXPIRED' | 'NOT_CONFIGURED'

const CHIP: Record<InductionState, { text: string; ok: boolean }> = {
  VERIFIED: { text: 'Induction verified', ok: true },
  PENDING: { text: 'Induction pending review', ok: false },
  NOT_SUBMITTED: { text: 'Induction not submitted', ok: false },
  REJECTED: { text: 'Induction rejected', ok: false },
  EXPIRED: { text: 'Induction expired', ok: false },
  NOT_CONFIGURED: { text: 'Not open for booking', ok: false },
}

const NOTE: Partial<Record<InductionState, string>> = {
  PENDING: 'You can request a booking once your induction is verified.',
  NOT_SUBMITTED: 'Submit induction to request a booking.',
  REJECTED: 'Resubmit induction to request a booking.',
  EXPIRED: 'Resubmit induction to request a booking.',
  NOT_CONFIGURED: 'No induction requirement is set up for this resource yet.',
}

export function ResourceCard({ resource, state, onOpen }: { resource: Resource; state: InductionState; onOpen: () => void }) {
  const chip = CHIP[state]
  const blocked = state === 'NOT_CONFIGURED'
  return (
    <article className="bk-rcard">
      <div className={`bk-cover ${resource.kind === 'ROOM' ? 'is-room' : 'is-equip'}`}>
        <span>{resource.name.slice(0, 1)}</span>
      </div>
      <div className="bk-rbody">
        <div>
          <span className="bk-kind">{resource.kind}</span>
          <h3>{resource.name}</h3>
          <p className="bk-loc"><PinIcon size={16} /> {resource.location}</p>
          <span className={`bk-chip ${chip.ok ? 'is-ok' : 'is-warn'}`}>
            {chip.ok ? <CheckIcon size={16} /> : <AlertIcon size={16} />} {chip.text}
          </span>
          {NOTE[state] && <p className="bk-note">{NOTE[state]}</p>}
        </div>
        <button className="bk-btn-outline" disabled={blocked} onClick={onOpen}>View availability</button>
      </div>
    </article>
  )
}
