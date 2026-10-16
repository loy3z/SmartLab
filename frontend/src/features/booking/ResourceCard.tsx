import { AlertIcon, CheckIcon, PinIcon } from './icons'
import type { Resource } from './types'

export type InductionState = 'VERIFIED' | 'PENDING' | 'NOT_SUBMITTED' | 'REJECTED' | 'EXPIRED' | 'NOT_CONFIGURED' | 'PREREQUISITE_REQUIRED'

const CHIP: Record<InductionState, { text: string; ok: boolean }> = {
  VERIFIED: { text: 'Induction verified', ok: true },
  PENDING: { text: 'Induction pending review', ok: false },
  NOT_SUBMITTED: { text: 'Induction not submitted', ok: false },
  REJECTED: { text: 'Induction rejected', ok: false },
  EXPIRED: { text: 'Induction expired', ok: false },
  NOT_CONFIGURED: { text: 'Not open for booking', ok: false },
  PREREQUISITE_REQUIRED: { text: 'Earlier induction needed first', ok: false },
}

const NOTE: Partial<Record<InductionState, string>> = {
  PENDING: 'You can request a booking once your induction is verified.',
  NOT_SUBMITTED: 'Submit induction to request a booking.',
  REJECTED: 'Resubmit induction to request a booking.',
  EXPIRED: 'Resubmit induction to request a booking.',
  NOT_CONFIGURED: 'No induction requirement is set up for this resource yet.',
}

const STATUS_TEXT = { MAINTENANCE: 'Under maintenance', CLOSED: 'Closed' } as const

interface Props {
  resource: Resource
  state: InductionState
  onOpen: () => void
  /** Rooms: how many devices are kept here, and a way to list them. */
  equipmentCount?: number
  onShowEquipment?: () => void
  /** Equipment: the name of the room it is kept in. */
  roomName?: string
  /** Name of the unverified prerequisite induction, when state is PREREQUISITE_REQUIRED. */
  prerequisiteName?: string
}

export function ResourceCard({ resource, state, onOpen, equipmentCount, onShowEquipment, roomName, prerequisiteName }: Props) {
  const chip = state === 'PREREQUISITE_REQUIRED' && prerequisiteName ? { text: `${prerequisiteName} needed first`, ok: false } : CHIP[state]
  const note = state === 'PREREQUISITE_REQUIRED'
    ? `Complete ${prerequisiteName ?? 'the earlier induction'} first, then the induction for this resource.`
    : NOTE[state]
  const unavailable = resource.status !== 'AVAILABLE'
  const blocked = state === 'NOT_CONFIGURED'
  return (
    <article className={`bk-rcard${unavailable ? ' is-unavailable' : ''}`}>
      <div className={`bk-cover ${resource.kind === 'ROOM' ? 'is-room' : 'is-equip'}`}>
        <span>{resource.name.slice(0, 1)}</span>
      </div>
      <div className="bk-rbody">
        <div>
          <span className="bk-kind">{resource.kind === 'ROOM' ? 'Room' : 'Equipment'}</span>
          <h3>{resource.name}</h3>
          <p className="bk-loc"><PinIcon size={16} /> {roomName ? `In ${roomName}` : resource.location}</p>
          {unavailable && (
            <div className="bk-unavailable" role="status">
              <strong>{STATUS_TEXT[resource.status as keyof typeof STATUS_TEXT]}</strong>
              {resource.status_reason && <span> — {resource.status_reason}</span>}
              <span className="bk-note"> New requests are paused; choose another {resource.kind === 'ROOM' ? 'room' : 'item'} or check back later.</span>
            </div>
          )}
          <span className={`bk-chip ${chip.ok ? 'is-ok' : 'is-warn'}`}>
            {chip.ok ? <CheckIcon size={16} /> : <AlertIcon size={16} />} {chip.text}
          </span>
          {!unavailable && note && <p className="bk-note">{note}</p>}
          {equipmentCount !== undefined && onShowEquipment && (
            <button type="button" className="bk-linkbtn" onClick={onShowEquipment}>
              {equipmentCount} {equipmentCount === 1 ? 'device' : 'devices'} in this room →
            </button>
          )}
        </div>
        <button className="bk-btn-outline" disabled={blocked} onClick={onOpen}>View availability</button>
      </div>
    </article>
  )
}
