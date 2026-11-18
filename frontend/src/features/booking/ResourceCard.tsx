// One resource (room or device) on the Book a resource page: where it is, its facts, whether this person's induction
// allows booking it, and the buttons that open the booking dialogs.
import { Link } from 'react-router'
import { fmtHours } from './format'
import { AlertIcon, CheckIcon, ClockIcon, PinIcon } from './icons'
import type { Resource } from '../../api/types/index.ts'

/** This person's induction state for the one resource (from the latest evidence for the induction it requires). */
export type InductionState = 'VERIFIED' | 'PENDING' | 'NOT_SUBMITTED' | 'REJECTED' | 'EXPIRED' | 'NOT_CONFIGURED' | 'PREREQUISITE_REQUIRED'

/** The status chip for each induction state (ok = green, otherwise amber). */
const CHIP: Record<InductionState, { text: string; ok: boolean }> = {
  VERIFIED: { text: 'Induction verified', ok: true },
  PENDING: { text: 'Induction pending review', ok: false },
  NOT_SUBMITTED: { text: 'Induction not submitted', ok: false },
  REJECTED: { text: 'Induction rejected', ok: false },
  EXPIRED: { text: 'Induction expired', ok: false },
  NOT_CONFIGURED: { text: 'Not open for booking', ok: false },
  PREREQUISITE_REQUIRED: { text: 'Earlier induction needed first', ok: false },
}

/** The short instruction under the chip; verified needs none. */
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
  /** The induction page for the evidence still to submit; makes the induction chip a link. */
  inductionHref?: string
  /** Staff only: book the same time every week. */
  onRepeat?: () => void
  onAdditionalHours?: () => void
  onLongBooking?: () => void
  testOverride?: boolean
  /** A Manager's booking skips induction and the normal length limit. */
  managerOverride?: boolean
  /** Replaces "View availability" (e.g. when the page was opened to request additional hours). */
  openLabel?: string
}

/** Overrides (test mode, Manager) change the chip and unblock the card; the server still enforces the real rules. */
export function ResourceCard({ resource, state, onOpen, equipmentCount, onShowEquipment, roomName, prerequisiteName, inductionHref, onRepeat, onAdditionalHours, onLongBooking, testOverride, managerOverride, openLabel }: Props) {
  // Make override priority explicit while preserving the existing badge behaviour.
  let chip = CHIP[state]

  if (testOverride) {
    chip = { text: 'Test override enabled', ok: true }
  } else if (managerOverride) {
    chip = { text: 'Manager booking: no induction needed', ok: true }
  } else if (state === 'PREREQUISITE_REQUIRED' && prerequisiteName) {
    chip = { text: `${prerequisiteName} needed first`, ok: false }
  }
  const note = state === 'PREREQUISITE_REQUIRED'
    ? `Complete ${prerequisiteName ?? 'the earlier induction'} first, then the induction for this resource.`
    : NOTE[state]
  // Under maintenance or closed: new requests are paused, but the room/device stays visible with the reason.
  const unavailable = resource.status !== 'AVAILABLE'
  const blocked = !testOverride && !managerOverride && state === 'NOT_CONFIGURED'
  const chipBody = <>{chip.ok ? <CheckIcon size={16} /> : <AlertIcon size={16} />} {chip.text}</>
  const chipClass = `bk-chip ${chip.ok ? 'is-ok' : 'is-warn'}`
  // The longest normal booking; a Manager may book up to the hard maximum.
  const longest = managerOverride ? resource.max_booking_minutes : resource.effective_max_booking_minutes ?? resource.max_booking_minutes
  return (
    <article className={`bk-rcard${unavailable ? ' is-unavailable' : ''}`}>
      <header className="resource-card-head">
        {/* No eyebrow label on rooms (the tab already says Rooms); equipment shows its category. */}
        <span className="resource-category">{resource.kind === 'EQUIPMENT' ? resource.category ?? '' : ''}</span>
        <span className={`bk-chip ${unavailable ? 'is-warn' : 'is-ok'}`}>{unavailable ? STATUS_TEXT[resource.status as keyof typeof STATUS_TEXT] : 'In service'}</span>
      </header>
      <div className="bk-rbody">
        <div className="bk-rcard-info">
          <div className="resource-identity"><div><h3>{resource.name}</h3>
            <p className="bk-loc"><PinIcon size={14} /> {roomName ? `In ${roomName}` : resource.location}</p></div>
            <span className="resource-outline" aria-hidden="true"><svg width="30" height="30" viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.1">{resource.kind === 'ROOM' ? <><path d="M4 5h24v22H4zM4 18h10V5M14 18h14M22 18v9"/><path d="M14 12a6 6 0 0 1 6 6" strokeDasharray="2 2"/><path d="M18 9h6v5h-6z"/></> : <><rect x="5" y="6" width="22" height="18" rx="2"/><path d="M10 13h12M10 17h7M12 27h8M16 24v3"/><circle cx="23" cy="20" r="1"/></>}</svg></span>
          </div>
          {/* Capacity and the first details, so people can choose without opening the form. */}
          <ResourceFacts resource={resource} limit={3} />
          {unavailable && (
            <div className="bk-unavailable" role="status">
              <strong>{STATUS_TEXT[resource.status as keyof typeof STATUS_TEXT]}</strong>
              {resource.status_reason && <span> — {resource.status_reason}</span>}
              <span className="bk-note">{testOverride ? ' Test overrides allow booking this resource.' : ` New requests are paused; choose another ${resource.kind === 'ROOM' ? 'room' : 'item'} or check back later.`}</span>
            </div>
          )}
          {inductionHref && !chip.ok
            ? <Link to={inductionHref} className={`${chipClass} bk-chip-link`}>{chipBody} →</Link>
            : <span className={chipClass}>{chipBody}</span>}
          {!testOverride && !managerOverride && !unavailable && note && <p className="bk-note">{note}</p>}
          {equipmentCount !== undefined && onShowEquipment && (
            <button type="button" className="bk-linkbtn" onClick={onShowEquipment}>
              {equipmentCount} {equipmentCount === 1 ? 'device' : 'devices'} in this room →
            </button>
          )}
        </div>
        <div className="resource-hours"><ClockIcon size={13} /><span>{fmtHours(resource.opening_time, resource.closing_time)}</span><span>Up to {longest / 60} h</span></div>
        <div className="bk-rcard-actions">
          <button type="button" className="bk-btn-outline bk-rcard-primary" disabled={blocked} onClick={onOpen}>{openLabel ?? 'View availability'}</button>
          {onAdditionalHours && <button type="button" className="bk-btn-outline" disabled={blocked || unavailable} onClick={onAdditionalHours}>Request additional hours</button>}
          {onLongBooking && resource.max_booking_minutes > (resource.effective_max_booking_minutes ?? resource.max_booking_minutes) &&
            <button type="button" className="bk-btn-outline" disabled={blocked || unavailable} onClick={onLongBooking}>Request a longer booking</button>}
          {onRepeat && (
            <button type="button" className="bk-btn-outline" disabled={blocked || (unavailable && !testOverride)} onClick={onRepeat}>Repeat weekly</button>
          )}
        </div>
      </div>
    </article>
  )
}

/** Room capacity and "label: value" details; limit shows only the first few (cards). */
export function ResourceFacts({ resource, limit }: { resource: Resource; limit?: number }) {
  const details = resource.details ?? []
  const shown = limit ? details.slice(0, limit) : details
  if (!resource.capacity && shown.length === 0) return null
  return (
    <dl className="bk-facts">
      {resource.capacity ? <div><dt>Capacity</dt><dd>Up to {resource.capacity} {resource.capacity === 1 ? 'person' : 'people'}</dd></div> : null}
      {shown.map((item, index) => <div key={index}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
      {limit && details.length > limit && <div className="bk-facts-more"><dd>+{details.length - limit} more in View availability</dd></div>}
    </dl>
  )
}
