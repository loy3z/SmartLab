// Sprint 3 (1.16.0): wording and rules for change requests on My Bookings (backend: services/changes.py).
import { fmtDateTime, fmtRange, STATUS_TEXT } from './format.ts'
import type { Booking } from '../../api/types/index.ts'

/** Whether to offer "Change time": the person's own approved booking that has not started and has no change waiting. */
export function canAskForChange(booking: Booking, userId: string | undefined, now: number): boolean {
  return Boolean(userId) && booking.student_id === userId && booking.status === 'APPROVED'
    && Date.parse(booking.start) > now && !booking.open_change && !booking.additional_hours && !booking.long_booking
}

/** Line on an approved booking that has a change waiting, e.g. "Change requested: Tue 4 Nov, 2:00 pm – 3:00 pm · Waitlisted". */
export function openChangeText(booking: Booking): string {
  const change = booking.open_change
  return change ? `Change requested: ${fmtRange(change.start, change.end)} · ${STATUS_TEXT[change.status]}` : ''
}

/** Line on the change request itself, naming the booking it would replace. */
export function replacesText(booking: Booking): string {
  const old = booking.replaces_booking
  if (!old) return ''
  return old.status === 'APPROVED'
    ? `Change request for your booking ${fmtRange(old.start, old.end)}. That booking stays until this one is approved.`
    : `Change request for your earlier booking ${fmtRange(old.start, old.end)}.`
}

/** Toast after a change request is accepted by the server. */
export function changeSentMessage(created: Booking): { title: string; message: string } {
  const when = fmtRange(created.start, created.end)
  if (created.status === 'APPROVED') {
    return { title: 'Booking moved', message: `${when} is approved. Your old time has been released.` }
  }
  if (created.status === 'WAITLISTED') {
    return { title: 'Change on the waitlist', message: `${when} is taken; if it frees up, an admin reviews your change. Your current booking stays.` }
  }
  return {
    title: 'Change requested',
    message: `${when}. Waiting for admin approval${created.review_due_at ? ` (decided by ${fmtDateTime(created.review_due_at)})` : ''}. Your current booking stays until then.`,
  }
}
