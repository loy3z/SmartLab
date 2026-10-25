// Sprint 3 (2026-10-25 cleanup): moved out of MyBookings.tsx so the page file stays readable.
import { useState } from 'react'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { rescheduleBooking } from './api'
import { errorMessage, fmtRange, minutesBetween, TZ } from './format'
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
