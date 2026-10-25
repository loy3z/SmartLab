// Sprint 3 (1.16.0): cards and labels of the staff "Today" page (TodayPage.tsx), kept here so they can be tested.
import type { Booking, StaffOverview } from '../booking/types.ts'

export interface TodoCard {
  key: string
  count: number
  label: string
  to: string
  /** red = needs action now, amber = waiting, grey = nothing to do */
  tone: 'red' | 'amber' | 'grey'
  hint?: string
}

/** One card per kind of waiting work, in the order staff usually handle them. Urgent requests say who decides. */
export function todoCards(data: StaffOverview): TodoCard[] {
  const tone = (count: number, urgent = false): TodoCard['tone'] => (count === 0 ? 'grey' : urgent ? 'red' : 'amber')
  return [
    { key: 'urgent', count: data.urgent_requests, label: 'Urgent requests', to: '/admin/bookings', tone: tone(data.urgent_requests, true),
      hint: data.can_decide_urgent ? 'Only a Manager decides these' : 'A Manager decides these' },
    { key: 'bookings', count: data.pending_bookings, label: 'Booking requests to decide', to: '/admin/bookings', tone: tone(data.pending_bookings, data.due_soon.length > 0),
      hint: data.due_soon.length ? `${data.due_soon.length} close to the deadline` : undefined },
    { key: 'changes', count: data.changes_waiting, label: 'Change requests', to: '/admin/bookings', tone: tone(data.changes_waiting),
      hint: 'People asking to move a booking' },
    { key: 'inductions', count: data.pending_inductions, label: 'Induction evidence to review', to: '/admin/qualifications', tone: tone(data.pending_inductions) },
    { key: 'unfreeze', count: data.unfreeze_requests, label: 'Unfreeze requests', to: '/admin/freezes', tone: tone(data.unfreeze_requests) },
    { key: 'waitlist', count: data.waitlisted, label: 'On the waitlist', to: '/admin/bookings', tone: 'grey' },
  ]
}

/** Attendance of one of today's bookings: checked in, missed, excused, or not yet (before/after its start). */
export function attendanceLabel(booking: Booking, now: number): string {
  switch (booking.attendance) {
    case 'CHECKED_IN': return 'Checked in'
    case 'NO_SHOW': return 'Missed'
    case 'EXCUSED': return 'Excused'
    case 'NOT_TRACKED': return 'Not tracked'
    default: return Date.parse(booking.start) > now ? 'Not started' : 'Not checked in yet'
  }
}
