// Sprint 3: check-in ("I'm here") helpers and the calendar link address.
import type { Attendance, Booking } from './types.ts'

export const ATTENDANCE_TEXT: Record<Attendance, string> = {
  CHECKED_IN: 'Checked in',
  NO_SHOW: 'Missed (no check-in)',
  EXCUSED: 'Not counted (resource unavailable)',
  NOT_TRACKED: '',
}

/** Whether this user may press "I'm here" on this booking now (only the person it is for). */
export function canCheckIn(booking: Booking, userId: string | undefined): boolean {
  return Boolean(userId && booking.check_in_open && booking.student_id === userId)
}

/** Hint for an approved booking that has not started: when check-in opens and closes. */
export function checkInHint(booking: Booking, now: number, fmt: (iso: string) => string): string {
  if (booking.status !== 'APPROVED' || booking.attendance || !booking.check_in_opens_at || !booking.check_in_closes_at) return ''
  if (Date.parse(booking.check_in_closes_at) <= now) return ''
  return `Check in on this page between ${fmt(booking.check_in_opens_at)} and ${fmt(booking.check_in_closes_at)}, or it counts as missed.`
}

/** Absolute subscription address from the API path (same site in development and production). */
export function calendarUrl(path: string, origin: string): string {
  return `${origin.replace(/\/+$/, '')}${path}`
}

/** Local date of a timestamp in Sydney, e.g. "12 Dec 2026". */
export function frozenUntilText(iso: string): string {
  return new Intl.DateTimeFormat('en-AU', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Australia/Sydney' }).format(new Date(iso))
}
