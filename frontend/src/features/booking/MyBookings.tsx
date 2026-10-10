import { useCallback, useEffect, useState } from 'react'
import { cancelBooking, listBookings, listResources, rescheduleBooking } from './api'
import { errorMessage, fmtDateTime, STATUS_TEXT } from './format'
import { SlotPicker } from './SlotPicker'
import type { Booking, Resource, Slot } from './types'

function RescheduleBox({ booking, resource, onDone }: { booking: Booking; resource: Resource; onDone: () => void }) {
  const [slot, setSlot] = useState<Slot | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const duration = (new Date(booking.end).getTime() - new Date(booking.start).getTime()) / 60000

  if (!open) return <button className="bk-btn-outline bk-sm" onClick={() => setOpen(true)}>Reschedule</button>

  async function save() {
    if (!slot) return
    setBusy(true)
    setError('')
    try {
      await rescheduleBooking(booking.id, slot.start, slot.end)
      onDone()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bk-resched">
      <p className="bk-muted">Pick a new start time ({duration} min, same length as now).</p>
      <SlotPicker
        resource={{ ...resource, slot_minutes: duration, max_booking_minutes: duration }}
        onSelect={setSlot}
        hideQualification
      />
      {slot && <p>New time: {fmtDateTime(slot.start)} → {fmtDateTime(slot.end)}</p>}
      <button className="bk-btn-yellow bk-sm" disabled={!slot || busy} onClick={save}>Confirm reschedule</button>{' '}
      <button className="bk-btn-outline bk-sm" onClick={() => setOpen(false)}>Close</button>
      {error && <p className="bk-error">{error}</p>}
    </div>
  )
}

export function MyBookings({ refreshKey }: { refreshKey: number }) {
  const [bookings, setBookings] = useState<Booking[]>([])
  const [resources, setResources] = useState<Record<string, Resource>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [now, setNow] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [b, r] = await Promise.all([listBookings(), listResources({})])
      setNow(Date.now())
      setBookings(b.results)
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
    if (!window.confirm('Cancel this booking?')) return
    try {
      await cancelBooking(b.id)
    } catch (e) {
      setError(errorMessage(e))
    }
    load()
  }

  const future = (b: Booking) => new Date(b.start).getTime() > now
  const cancellable = (b: Booking) =>
    future(b) && ['WAITING_QUALIFICATION', 'WAITLISTED', 'PENDING_APPROVAL', 'APPROVED'].includes(b.status)

  return (
    <div>
      <h1>My bookings</h1>
      <p className="bk-sub">Your requests and their current status.</p>
      {loading && <p>Loading…</p>}
      {error && <p className="bk-error">{error}</p>}
      {!loading && bookings.length === 0 && <p>No bookings yet.</p>}
      {bookings.map((b) => {
        const res = resources[b.resource_id]
        return (
          <div key={b.id} className="bk-bcard">
            <div className="bk-bhead"><h3>{res?.name ?? 'Resource'}</h3><span className={`bk-chip st-${b.status}`}>{STATUS_TEXT[b.status]}</span></div>
            <p>
              {fmtDateTime(b.start)} → {fmtDateTime(b.end)}
            </p>
            {b.hold_active && b.hold_until && <p className="bk-muted">Time held until {fmtDateTime(b.hold_until)}</p>}
            {b.purpose && <p className="bk-muted">Purpose: {b.purpose}</p>}
            {b.decision_reason && <p className="bk-muted">Reason: {b.decision_reason}</p>}
            {b.outlook_sync?.status === 'SYNCED' && b.outlook_sync.web_link && (
              <p><a href={b.outlook_sync.web_link} target="_blank" rel="noreferrer">Open calendar</a></p>
            )}
            {b.outlook_sync?.status === 'FAILED' && (
              <p className="bk-muted">Calendar sync failed; your booking is unaffected. Contact an admin.</p>
            )}
            {cancellable(b) && <button className="bk-btn-outline bk-sm" onClick={() => cancel(b)}>Cancel</button>}
            {b.status === 'APPROVED' && future(b) && res && (
              <RescheduleBox booking={b} resource={res} onDone={load} />
            )}
          </div>
        )
      })}
    </div>
  )
}
