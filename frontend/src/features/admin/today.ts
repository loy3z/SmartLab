// Sprint 3 (1.16.0): cards and labels of the staff "Today" page (TodayPage.tsx), kept here so they can be tested.
import type { Booking, StaffOverview } from '../../api/types/index.ts'

export interface TodoCard {
  key: string
  count: number
  label: string
  to: string
  /** red = needs action now, amber = waiting, grey = nothing to do */
  tone: 'red' | 'amber' | 'grey'
  hint?: string
}

/** 2026-11-07 (client, Week 8): cards only a Manager can act on. Admins do not see them on Today; the Manager home
 *  page shows them first. */
export const MANAGER_DECIDES = ['extensions', 'urgent', 'additional-hours', 'long-bookings']

/** The cards of Today for this role: an Admin's review work, or everything for a Manager. */
export function cardsFor(data: StaffOverview): TodoCard[] {
  return todoCards(data).filter((card) => data.role === 'MANAGER' || !MANAGER_DECIDES.includes(card.key))
}

/** One card per kind of waiting work, in the order staff usually handle them. Urgent requests say who decides. */
export function todoCards(data: StaffOverview): TodoCard[] {
  const tone = (count: number, urgent = false): TodoCard['tone'] => (count === 0 ? 'grey' : urgent ? 'red' : 'amber')
  const extensions = data.extension_requests?.length ?? 0
  return [
    // 2026-11-07: the person is in the lab now, so these come first.
    { key: 'extensions', count: extensions, label: 'Extension requests', to: '/manager/home?focus=extensions', tone: tone(extensions, true),
      hint: 'Someone in the lab asks to stay longer' },
    { key: 'urgent', count: data.urgent_requests, label: 'Urgent requests', to: '/admin/bookings', tone: tone(data.urgent_requests, true),
      hint: data.can_decide_urgent ? 'Only a Manager decides these' : 'A Manager decides these' },
    { key: 'additional-hours', count: data.additional_hours_requests ?? 0, label: 'Additional-hours requests', to: '/admin/bookings?type=additional-hours', tone: tone(data.additional_hours_requests ?? 0),
      hint: data.can_decide_additional_hours ? `${data.additional_hours_ready ?? 0} ready for Manager approval` : 'A Manager decides these; pending requests do not hold time' },
    { key: 'long-bookings', count: data.long_booking_requests ?? 0, label: 'Long-booking requests', to: '/admin/bookings?type=long-bookings', tone: tone(data.long_booking_requests ?? 0),
      hint: data.can_decide_long_bookings ? 'Decide before the review deadline; never automatic' : 'Only a Manager can decide these' },
    { key: 'bookings', count: data.pending_bookings, label: 'Booking requests to decide', to: '/admin/bookings', tone: tone(data.pending_bookings, data.due_soon.length > 0),
      hint: data.due_soon.length ? `${data.due_soon.length} close to the deadline` : undefined },
    { key: 'changes', count: data.changes_waiting, label: 'Change requests', to: '/admin/bookings', tone: tone(data.changes_waiting),
      hint: 'People asking to move a booking' },
    { key: 'inductions', count: data.pending_inductions, label: 'Induction evidence to review', to: '/admin/qualifications', tone: tone(data.pending_inductions) },
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
