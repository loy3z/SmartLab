import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { EmptyState, Tabs } from '../../ui/components'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { cancelBooking, cancelSeries, checkIn, listBookings, listResources, rescheduleBooking } from './api'
import { ATTENDANCE_TEXT, canCheckIn, checkInHint } from './attendance'
import { CalendarSubscribe } from './CalendarSubscribe'
import { ChangeTimeBox } from './ChangeTimeBox' // Sprint 3 (1.16.0)
import { canAskForChange, openChangeText, replacesText } from './change-requests' // Sprint 3 (1.16.0)
import { ContactLink } from '../contact/LabContact' // Sprint 3 (1.16.0)
import { FreezeNotice } from './FreezeNotice'
import { bookingDetail, errorMessage, fmtDay, fmtDuration, fmtRange, fmtTime, minutesBetween, STATUS_TEXT, TZ } from './format'
import { groupBookings, seriesSummary } from './my-bookings'
import { SlotPicker, type SlotRange } from './SlotPicker'
import type { Booking, Resource } from './types'

/** Manager only: move an approved booking. The minimum advance window does not apply. */
export function RescheduleBox({ booking, resource, onDone, onClose }: {
  booking: Booking
  resource: Resource
  onDone: (updated: Booking) => void
  onClose: () => void
}) {
  const feedback = useFeedback()
  const { user } = useAuth()
  const [range, setRange] = useState<SlotRange | null>(null)
  const [busy, setBusy] = useState(false)
  // Sprint 3 (review R1): Room Management shows this box in a Modal, where a toast is hidden under the backdrop.
  const [error, setError] = useState('')
  const duration = minutesBetween(booking.start, booking.end)

  async function save() {
    if (!range) return
    setError('')
    const ok = await feedback.confirm({
      title: 'Move this booking?',
      details: [
        { label: 'From', value: fmtRange(booking.start, booking.end) },
        { label: 'To', value: fmtRange(range.start, range.end) },
      ],
      confirmLabel: 'Move booking',
    })
    if (!ok.confirmed) return
    setBusy(true)
    try {
      onDone(await rescheduleBooking(booking.id, range.start, range.end))
    } catch (e) {
      const text = errorMessage(e)
      setError(text)
      feedback.error(text, 'Booking not moved')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bk-resched">
      <SlotPicker resource={resource} onSelect={(picked) => { setRange(picked); setError('') }} hideQualification fixedMinutes={duration} excludeBookingId={booking.id}
        forZid={booking.student_id === user?.id ? undefined : booking.booked_for?.zid ?? booking.student?.zid} allowEarly
        initialDate={new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date(booking.start))} />
      {error && <p className="bk-error" role="alert">Booking not moved: {error}</p>}
      <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
        <button className="ui-btn ui-btn-primary ui-btn-sm" disabled={!range || busy} onClick={save}>{busy ? 'Saving…' : 'Confirm new time'}</button>
        <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose}>Close</button>
      </div>
    </div>
  )
}

const ACTIVE = ['WAITING_QUALIFICATION', 'WAITLISTED', 'PENDING_APPROVAL', 'APPROVED']
const BOOKING_VIEWS = [
  { key: 'all', label: 'All bookings' }, { key: 'upcoming', label: 'Upcoming' },
  { key: 'pending', label: 'Pending' }, { key: 'past', label: 'Past' }, { key: 'cancelled', label: 'Cancelled' },
] as const
type BookingView = typeof BOOKING_VIEWS[number]['key']

function inView(booking: Booking, view: BookingView, now: number) {
  if (view === 'all') return true
  if (view === 'cancelled') return booking.status === 'CANCELLED'
  if (view === 'upcoming') return booking.status === 'APPROVED' && Date.parse(booking.end) > now
  if (view === 'pending') return ['PENDING_APPROVAL', 'WAITLISTED', 'WAITING_QUALIFICATION'].includes(booking.status)
  return booking.status !== 'CANCELLED' && (Date.parse(booking.end) <= now || ['REJECTED', 'EXPIRED'].includes(booking.status))
}

/**
 * Sprint 3: a weekly series as one card. Shows the pattern, date range, how many dates are left and the next date;
 * the "I'm here" button of today's date comes up to the card. "Show dates" lists every date, each cancellable on
 * its own; staff can cancel the rest of the series at once.
 */
function SeriesCard({ bookings, resource, userId, now, isStaff, isManager, onCancel, onCancelRest, onCheckIn, onReschedule }: {
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

export function MyBookings({ refreshKey }: { refreshKey: number }) {
  const feedback = useFeedback()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const view = BOOKING_VIEWS.find(item => item.key === params.get('view'))?.key ?? 'all'
  const isManager = user?.role === 'MANAGER'
  const isStaff = user?.role === 'MANAGER' || user?.role === 'ADMIN'
  const [bookings, setBookings] = useState<Booking[]>([])
  const [resources, setResources] = useState<Record<string, Resource>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [now, setNow] = useState(0)
  const [rescheduling, setRescheduling] = useState<string | null>(null)
  const [changing, setChanging] = useState<string | null>(null) // Sprint 3 (1.16.0): booking whose change box is open

  const load = useCallback(async () => {
    setError('')
    try {
      const [b, r] = await Promise.all([listBookings(), listResources({})])
      setNow(Date.now())
      setBookings([...b.results].sort((x, y) => Date.parse(y.created_at) - Date.parse(x.created_at)))
      setResources(Object.fromEntries(r.results.map((x) => [x.id, x])))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
  }, [load, refreshKey])

  async function cancel(b: Booking) {
    const name = resources[b.resource_id]?.name ?? 'this resource'
    const ok = await feedback.confirm({
      title: b.status === 'APPROVED' ? 'Cancel this booking?' : 'Withdraw this request?',
      details: [{ label: 'Resource', value: name }, { label: 'Time', value: fmtRange(b.start, b.end) }],
      message: 'The time is released for other students. This cannot be undone.',
      confirmLabel: b.status === 'APPROVED' ? 'Cancel booking' : 'Withdraw request',
      cancelLabel: 'Keep it',
      danger: true,
    })
    if (!ok.confirmed) return
    try {
      await cancelBooking(b.id)
      feedback.success(`${name}, ${fmtRange(b.start, b.end)}`, b.status === 'APPROVED' ? 'Booking cancelled' : 'Request withdrawn')
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not cancel')
    }
    await load()
  }

  // Sprint 3: check-in and cancelling a weekly series
  async function arrived(b: Booking) {
    try {
      await checkIn(b.id)
      feedback.success(`${resources[b.resource_id]?.name ?? 'Booking'}, ${fmtRange(b.start, b.end)}`, 'Checked in')
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not check in')
    }
    await load()
  }

  async function cancelWholeSeries(b: Booking) {
    if (!b.series_id) return
    const ok = await feedback.confirm({
      title: 'Cancel the rest of this weekly series?',
      details: [{ label: 'Resource', value: resources[b.resource_id]?.name ?? 'Resource' }],
      message: 'Every future date of the series is cancelled and the times are released. Past dates stay as they are.',
      confirmLabel: 'Cancel series',
      cancelLabel: 'Keep it',
      danger: true,
    })
    if (!ok.confirmed) return
    try {
      const series = await cancelSeries(b.series_id)
      feedback.success(`${series.bookings.filter((item) => item.status === 'CANCELLED').length} date(s) cancelled.`, 'Series cancelled')
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not cancel the series')
    }
    await load()
  }

  async function rescheduled(b: Booking) {
    setRescheduling(null)
    const calendar = b.outlook_sync && b.outlook_sync.status !== 'DISABLED' && b.outlook_sync.status !== 'NOT_REQUIRED'
    feedback.success(`New time: ${fmtRange(b.start, b.end)}.${calendar ? ' Your calendar event will be updated.' : ''}`, 'Booking moved')
    await load()
  }

  const future = (b: Booking) => new Date(b.start).getTime() > now
  const cancellable = (b: Booking) => future(b) && ACTIVE.includes(b.status)
  const shown = bookings.filter(booking => inView(booking, view, now))

  return (
    <div className="bookings-list">
      <h1>My bookings</h1>{/* Sprint 3 (internal-tool UI, AI-2): no introduction line */}
      {/* Sprint 3 */}
      <FreezeNotice />
      <CalendarSubscribe />
      {!loading && !error && <div className="bookings-filters"><Tabs value={view} onChange={next => setParams({ view: next })} label="Booking status" items={BOOKING_VIEWS.map(item => ({ ...item, count: bookings.filter(booking => inView(booking, item.key, now)).length }))} /></div>}
      {loading && <p role="status">Loading…</p>}
      {error && <p className="bk-error" role="alert">{error}</p>}
      {!loading && !error && bookings.length === 0 && (
        <EmptyState icon="+" title="No bookings yet">
          <Link to="/resources">Browse rooms and equipment</Link> to make your first request.
        </EmptyState>
      )}
      {!loading && !error && bookings.length > 0 && shown.length === 0 && <EmptyState title="Nothing here right now">No bookings match this view. Your other bookings are in All bookings.</EmptyState>}
      {groupBookings(shown).map((group) => {
        if (group.kind === 'series') {
          const moving = group.bookings.find((item) => item.id === rescheduling)
          const seriesResource = resources[group.bookings[0].resource_id]
          return (
            <div key={group.seriesId}>
              <SeriesCard bookings={group.bookings} resource={seriesResource} userId={user?.id} now={now}
                isStaff={isStaff} isManager={isManager} onCancel={(b) => void cancel(b)} onCancelRest={(b) => void cancelWholeSeries(b)}
                onCheckIn={(b) => void arrived(b)} onReschedule={(b) => setRescheduling(b.id)} />
              {moving && seriesResource && (
                <RescheduleBox booking={moving} resource={seriesResource} onDone={rescheduled} onClose={() => setRescheduling(null)} />
              )}
            </div>
          )
        }
        const b = group.booking
        const res = resources[b.resource_id]
        return (
          <div key={b.id} className="bk-bcard">
            <div className="bk-bhead">
              <h3>{res?.name ?? 'Resource'}</h3>
              <span className={`bk-chip st-${b.status}`}>{STATUS_TEXT[b.status]}{b.status === 'WAITLISTED' && b.waitlist_position ? ` · #${b.waitlist_position}` : ''}</span>
              {b.urgent && <span className="bk-chip is-urgent">URGENT</span>}
              {b.attendance && ATTENDANCE_TEXT[b.attendance] && (
                <span className={`bk-chip att-${b.attendance}`}>{ATTENDANCE_TEXT[b.attendance]}</span>
              )}
            </div>
            {b.on_behalf && (
              <p className="bk-muted">
                {b.booked_for?.id === user?.id
                  ? `Booked for you by ${b.created_by_user?.display_name ?? 'staff'} (${b.created_by_user?.zid ?? ''})`
                  : `For ${b.booked_for?.display_name ?? 'someone else'} (${b.booked_for?.zid ?? ''}), created by you`}
              </p>
            )}
            {b.urgent && b.urgent_reason && <p className="bk-muted">Urgent because: {b.urgent_reason}</p>}
            <p><b>{fmtRange(b.start, b.end)}</b> <span className="bk-muted">· {fmtDuration(minutesBetween(b.start, b.end))}</span></p>
            <p className="bk-muted">{bookingDetail(b)}</p>
            {b.purpose && !(b.urgent && b.purpose === b.urgent_reason) && <p className="bk-muted">Purpose: {b.purpose}</p>}
            {/* Sprint 3 (1.16.0): change requests */}
            {b.replaces_booking && <p className="bk-change-note">{replacesText(b)}</p>}
            {b.open_change && <p className="bk-change-note">{openChangeText(b)}</p>}
            {b.outlook_sync?.status === 'SYNCED' && b.outlook_sync.web_link && (
              <p><a href={b.outlook_sync.web_link} target="_blank" rel="noreferrer">Open calendar</a></p>
            )}
            {canCheckIn(b, user?.id) ? (
              <div className="bk-checkin">
                <button className="ui-btn ui-btn-primary ui-btn-sm" onClick={() => void arrived(b)}>I'm here</button>
                <span className="bk-muted">Confirm you are at the {res?.kind === 'EQUIPMENT' ? 'equipment' : 'room'} now.</span>
              </div>
            ) : b.student_id === user?.id && checkInHint(b, now, fmtTime) ? (
              <p className="bk-muted">{checkInHint(b, now, fmtTime)}</p>
            ) : null}
            {b.outlook_sync?.status === 'FAILED' && (
              <p className="bk-muted">Calendar sync failed; your booking is unaffected. Contact an admin.</p>
            )}
            {(cancellable(b) || (isManager && b.status === 'APPROVED' && future(b) && res)) && rescheduling !== b.id && changing !== b.id && (
              <div className="bk-card-actions">
                {isManager && b.status === 'APPROVED' && future(b) && res && (
                  <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setRescheduling(b.id)}>Reschedule</button>
                )}
                {/* Sprint 3 (1.16.0): everyone else asks for a new time; Managers move bookings directly. */}
                {!isManager && res && canAskForChange(b, user?.id, now) && (
                  <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setChanging(b.id)}>Change time</button>
                )}
                {cancellable(b) && (
                  <button className="ui-btn ui-btn-reject ui-btn-sm" onClick={() => cancel(b)}>
                    {b.status === 'APPROVED' ? 'Cancel booking' : b.replaces_booking ? 'Withdraw change request' : 'Withdraw request'}
                  </button>
                )}
                {/* Sprint 3 (1.16.0): email the lab with the booking already named (only when the lab gave an email) */}
                {b.status === 'APPROVED' && future(b) && (
                  <ContactLink label="Contact the lab" subject={`SmartLab booking: ${res?.name ?? 'Resource'}, ${fmtRange(b.start, b.end)}`}
                    body={`Booking reference: ${b.id}\nResource: ${res?.name ?? ''}\nTime: ${fmtRange(b.start, b.end)}\n\n`} />
                )}
              </div>
            )}
            {rescheduling === b.id && res && (
              <RescheduleBox booking={b} resource={res} onDone={rescheduled} onClose={() => setRescheduling(null)} />
            )}
            {changing === b.id && res && (
              <ChangeTimeBox booking={b} resource={res} onDone={() => { setChanging(null); void load() }} onClose={() => setChanging(null)} />
            )}
          </div>
        )
      })}
    </div>
  )
}
