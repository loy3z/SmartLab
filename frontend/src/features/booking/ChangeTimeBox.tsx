// Sprint 3 (1.16.0): the person a booking is for asks for a new time (backend: services/changes.py).
import { useState } from 'react'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { requestTimeChange } from '../../api/index.ts'
import { changeSentMessage } from './change-requests'
import { errorMessage, fmtRange, TZ } from './format'
import { SlotPicker, type SlotRange } from './SlotPicker'
import type { Booking, Resource } from '../../api/types/index.ts'

/**
 * Pick a new time for an approved booking on the same resource. Free time is sent for review; time someone else
 * has booked can only join the waitlist (said before sending). The current booking stays until the new time is
 * approved, then it is released automatically.
 */
export function ChangeTimeBox({ booking, resource, onDone, onClose }: {
  booking: Booking
  resource: Resource
  onDone: () => void
  onClose: () => void
}) {
  const feedback = useFeedback()
  const { user } = useAuth()
  const testBypass = Boolean(user?.bypass_booking_rules && booking.student_id === user.id)
  const [range, setRange] = useState<SlotRange | null>(null)
  const [busy, setBusy] = useState(false)

  async function send() {
    if (!range) return
    const ok = await feedback.confirm({
      title: testBypass ? 'Move your test booking?' : range.overlapsTaken ? 'Join the waitlist for this time?' : 'Ask for this time?',
      details: [
        { label: 'Now', value: fmtRange(booking.start, booking.end) },
        { label: 'Wanted', value: fmtRange(range.start, range.end) },
      ],
      message: testBypass ? 'Test overrides are on. The new time is approved immediately and your old time is released.' : range.overlapsTaken
        ? 'Someone else has booked this time, so your change waits on the waitlist. Your current booking stays until the new time is approved.'
        : 'An admin reviews the change. Your current booking stays until the new time is approved, then it is released.',
      confirmLabel: testBypass ? 'Move booking' : range.overlapsTaken ? 'Join waitlist' : 'Send change request',
      cancelLabel: 'Back',
    })
    if (!ok.confirmed) return
    setBusy(true)
    try {
      const created = await requestTimeChange(booking.id, range.start, range.end)
      const { title, message } = changeSentMessage(created)
      feedback.success(message, title)
      onDone()
    } catch (e) {
      feedback.error(errorMessage(e), 'Change not sent')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bk-resched">
      <p className="bk-muted">{testBypass ? 'Choose a free future time. Test overrides approve the move immediately and release your old time.' : <>Choose the new time. Your current booking ({fmtRange(booking.start, booking.end)}) stays until the new time is approved.</>}</p>
      <SlotPicker resource={resource} onSelect={setRange} hideQualification excludeBookingId={booking.id}
        initialDate={new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date(booking.start))}
        takenNote="This time is already booked by someone else, so your change can only join the waitlist. If the time frees up, an admin reviews it; until then your current booking stays." />
      <div className="bk-resched-actions">
        <button className="ui-btn ui-btn-primary ui-btn-sm" disabled={!range || busy} onClick={() => void send()}>
          {busy ? 'Sending…' : testBypass ? 'Move booking' : range?.overlapsTaken ? 'Join the waitlist for this time' : 'Ask for this time'}
        </button>
        <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose}>Close</button>
        {!range && <span className="bk-missing" role="status">Choose a new time above.</span>}
      </div>
    </div>
  )
}
