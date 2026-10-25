import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { EmptyState, Tabs } from '../../ui/components'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { cancelBooking, cancelSeries, checkIn, listBookings, listResources } from './api'
import { ATTENDANCE_TEXT, canCheckIn, checkInHint } from './attendance'
import { CalendarSubscribe } from './CalendarSubscribe'
import { ChangeTimeBox } from './ChangeTimeBox' // Sprint 3 (1.16.0)
import { canAskForChange, openChangeText, replacesText } from './change-requests' // Sprint 3 (1.16.0)
import { ContactLink } from '../contact/LabContact' // Sprint 3 (1.16.0)
import { FreezeNotice } from './FreezeNotice'
import { bookingDetail, errorMessage, fmtDuration, fmtRange, fmtTime, minutesBetween, STATUS_TEXT } from './format'
import { ACTIVE, groupBookings } from './my-bookings'
import { RescheduleBox } from './RescheduleBox'
import { SeriesCard } from './SeriesCard'
import type { Booking, Resource } from './types'


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
