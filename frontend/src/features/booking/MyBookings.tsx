import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { EmptyState } from '../../ui/components'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { cancelBooking, listBookings, listResources, rescheduleBooking } from './api'
import { bookingDetail, errorMessage, fmtDuration, fmtRange, minutesBetween, STATUS_TEXT, TZ } from './format'
import { SlotPicker, type SlotRange } from './SlotPicker'
import type { Booking, Resource } from './types'

/** Manager only (client, 17 Oct): move an approved booking. The minimum advance window does not apply. */
export function RescheduleBox({ booking, resource, onDone, onClose }: {
  booking: Booking
  resource: Resource
  onDone: (updated: Booking) => void
  onClose: () => void
}) {
  const feedback = useFeedback()
  const [range, setRange] = useState<SlotRange | null>(null)
  const [busy, setBusy] = useState(false)
  const duration = minutesBetween(booking.start, booking.end)

  async function save() {
    if (!range) return
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
      feedback.error(errorMessage(e), 'Booking not moved')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bk-resched">
      <SlotPicker resource={resource} onSelect={setRange} hideQualification fixedMinutes={duration} excludeBookingId={booking.id}
        forZid={booking.booked_for?.zid ?? booking.student?.zid} allowEarly
        initialDate={new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date(booking.start))} />
      <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
        <button className="ui-btn ui-btn-primary ui-btn-sm" disabled={!range || busy} onClick={save}>{busy ? 'Saving…' : 'Confirm new time'}</button>
        <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose}>Close</button>
      </div>
    </div>
  )
}

const ACTIVE = ['WAITING_QUALIFICATION', 'WAITLISTED', 'PENDING_APPROVAL', 'APPROVED']

export function MyBookings({ refreshKey }: { refreshKey: number }) {
  const feedback = useFeedback()
  const { user } = useAuth()
  const isManager = user?.role === 'MANAGER'
  const [bookings, setBookings] = useState<Booking[]>([])
  const [resources, setResources] = useState<Record<string, Resource>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [now, setNow] = useState(0)
  const [rescheduling, setRescheduling] = useState<string | null>(null)

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

  async function rescheduled(b: Booking) {
    setRescheduling(null)
    const calendar = b.outlook_sync && b.outlook_sync.status !== 'DISABLED' && b.outlook_sync.status !== 'NOT_REQUIRED'
    feedback.success(`New time: ${fmtRange(b.start, b.end)}.${calendar ? ' Your calendar event will be updated.' : ''}`, 'Booking moved')
    await load()
  }

  const future = (b: Booking) => new Date(b.start).getTime() > now
  const cancellable = (b: Booking) => future(b) && ACTIVE.includes(b.status)

  return (
    <div>
      <h1>My bookings</h1>
      <p className="bk-sub">{user?.role === 'STUDENT' ? 'Your requests and their current status.' : 'Your own requests and those you made for other people.'}</p>
      {loading && <p role="status">Loading…</p>}
      {error && <p className="bk-error" role="alert">{error}</p>}
      {!loading && !error && bookings.length === 0 && (
        <EmptyState icon="+" title="No bookings yet">
          <Link to="/resources">Browse rooms and equipment</Link> to make your first request.
        </EmptyState>
      )}
      {bookings.map((b) => {
        const res = resources[b.resource_id]
        return (
          <div key={b.id} className="bk-bcard">
            <div className="bk-bhead">
              <h3>{res?.name ?? 'Resource'}</h3>
              <span className={`bk-chip st-${b.status}`}>{STATUS_TEXT[b.status]}{b.status === 'WAITLISTED' && b.waitlist_position ? ` · #${b.waitlist_position}` : ''}</span>
              {b.urgent && <span className="bk-chip is-urgent">URGENT</span>}
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
            {b.purpose && <p className="bk-muted">Purpose: {b.purpose}</p>}
            {b.outlook_sync?.status === 'SYNCED' && b.outlook_sync.web_link && (
              <p><a href={b.outlook_sync.web_link} target="_blank" rel="noreferrer">Open calendar</a></p>
            )}
            {b.outlook_sync?.status === 'FAILED' && (
              <p className="bk-muted">Calendar sync failed; your booking is unaffected. Contact an admin.</p>
            )}
            {(cancellable(b) || (isManager && b.status === 'APPROVED' && future(b) && res)) && rescheduling !== b.id && (
              <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                {isManager && b.status === 'APPROVED' && future(b) && res && (
                  <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setRescheduling(b.id)}>Reschedule</button>
                )}
                {cancellable(b) && (
                  <button className="ui-btn ui-btn-reject ui-btn-sm" onClick={() => cancel(b)}>
                    {b.status === 'APPROVED' ? 'Cancel booking' : 'Withdraw request'}
                  </button>
                )}
              </div>
            )}
            {rescheduling === b.id && res && (
              <RescheduleBox booking={b} resource={res} onDone={rescheduled} onClose={() => setRescheduling(null)} />
            )}
          </div>
        )
      })}
    </div>
  )
}
