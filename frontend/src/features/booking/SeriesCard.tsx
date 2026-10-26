// Sprint 3 (2026-10-25 cleanup): moved out of MyBookings.tsx so the page file stays readable.
import { useState } from 'react'
import { ATTENDANCE_TEXT, canCheckIn, checkInHint } from './attendance'
import { fmtDay, fmtDuration, fmtRange, fmtTime, minutesBetween, STATUS_TEXT } from './format'
import { ACTIVE, seriesSummary } from './my-bookings'
import type { Booking, Resource } from '../../api/types/index.ts'

/**
 * Sprint 3: a weekly series as one card. Shows the pattern, date range, how many dates are left and the next date;
 * the "I'm here" button of today's date comes up to the card. "Show dates" lists every date, each cancellable on
 * its own; staff can cancel the rest of the series at once.
 */
export function SeriesCard({ bookings, resource, userId, now, isStaff, isManager, onCancel, onCancelRest, onCheckIn, onReschedule }: {
  bookings: Booking[]
  resource: Resource | undefined
  userId: string | undefined
  now: number
  isStaff: boolean
  isManager: boolean
  onCancel: (b: Booking) => void
  onCancelRest: (b: Booking) => void
  onCheckIn: (b: Booking) => void
  onReschedule: (b: Booking) => void
}) {
  const [open, setOpen] = useState(false)
  const summary = seriesSummary(bookings, now)
  const first = bookings[0]
  const dueNow = bookings.find((item) => canCheckIn(item, userId))
  const hint = summary.next && summary.next.student_id === userId ? checkInHint(summary.next, now, fmtTime) : ''
  const isFuture = (b: Booking) => Date.parse(b.start) > now
  const cancellable = (b: Booking) => isFuture(b) && ACTIVE.includes(b.status)
  const someCancellable = bookings.some(cancellable)
  return (
    <div className="bk-bcard bk-series-card">
      <div className="bk-bhead">
        <h3>{resource?.name ?? 'Resource'}</h3>
        <span className="bk-chip is-series">Weekly series</span>
        {summary.remaining > 0 ? <span className="bk-chip st-APPROVED">Approved</span> : <span className="bk-chip">Finished</span>}
      </div>
      {first.on_behalf && (
        <p className="bk-muted">
          {first.booked_for?.id === userId
            ? `Booked for you by ${first.created_by_user?.display_name ?? 'staff'} (${first.created_by_user?.zid ?? ''})`
            : `For ${first.booked_for?.display_name ?? 'someone else'} (${first.booked_for?.zid ?? ''}), created by you`}
        </p>
      )}
      <p><b>{summary.pattern}</b> <span className="bk-muted">· {fmtDuration(minutesBetween(first.start, first.end))} each</span></p>
      <p className="bk-muted">
        {fmtDay(summary.firstStart)} – {fmtDay(summary.lastStart)} · {summary.remaining} of {summary.total} dates left
        {summary.cancelled ? ` · ${summary.cancelled} cancelled` : ''}
      </p>
      <p>{summary.next ? <>Next: <b>{fmtRange(summary.next.start, summary.next.end)}</b></> : <span className="bk-muted">No dates left.</span>}</p>
      {first.purpose && <p className="bk-muted">Purpose: {first.purpose}</p>}
      {dueNow ? (
        <div className="bk-checkin">
          <button className="ui-btn ui-btn-primary ui-btn-sm" onClick={() => onCheckIn(dueNow)}>I'm here</button>
          <span className="bk-muted">For {fmtRange(dueNow.start, dueNow.end)}.</span>
        </div>
      ) : hint ? <p className="bk-muted">{hint}</p> : null}
      <div style={{ display: 'flex', gap: 10, marginTop: 4, flexWrap: 'wrap' }}>
        <button className="ui-btn ui-btn-ghost ui-btn-sm" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Hide dates' : `Show dates (${summary.total})`}
        </button>
        {isStaff && someCancellable && (
          <button className="ui-btn ui-btn-reject ui-btn-sm" onClick={() => onCancelRest(first)}>Cancel the rest</button>
        )}
      </div>
      {open && (
        <ul className="bk-series-dates" aria-label="Series dates">
          {bookings.map((b) => (
            <li key={b.id}>
              <span>{fmtRange(b.start, b.end)}</span>
              <span className={`bk-chip st-${b.status}`}>{STATUS_TEXT[b.status]}</span>
              {b.attendance && ATTENDANCE_TEXT[b.attendance] && <span className={`bk-chip att-${b.attendance}`}>{ATTENDANCE_TEXT[b.attendance]}</span>}
              <span className="bk-series-actions">
                {isManager && b.status === 'APPROVED' && isFuture(b) && resource && (
                  <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => onReschedule(b)}>Reschedule</button>
                )}
                {cancellable(b) && <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => onCancel(b)}>Cancel this date</button>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
