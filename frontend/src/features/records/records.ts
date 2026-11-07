// Sprint 3: Booking Records page (Admin and Manager): filters -> API query, and the text shown in each column.
import { ATTENDANCE_TEXT } from '../booking/attendance.ts'
import type { Booking } from '../../api/types/index.ts'

const SYDNEY = 'Australia/Sydney'

export interface RecordFilters {
  /** "YYYY-MM-DD" (Sydney dates, both included). */
  from: string
  to: string
  resourceId: string
  /** Part of a zID or name: the person booked for or whoever created the booking. */
  q: string
  /** One booking status, or "ALL". */
  status: string
}

export const RECORD_STATUSES: { value: string; label: string }[] = [
  { value: 'ALL', label: 'All statuses' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'PENDING_APPROVAL', label: 'Waiting for approval' },
  { value: 'WAITLISTED', label: 'Waitlisted' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'EXPIRED', label: 'Expired' },
]

export function addDays(ymd: string, days: number): string {
  const value = new Date(`${ymd}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}

/** Admins see bookings that ended at most this many days ago (server: ADMIN_HISTORY_DAYS, 2026-11-07). */
export const ADMIN_HISTORY_DAYS = 7

/** Recent history (30 days for a Manager, the Admin limit for an Admin) to 30 days ahead. A zID lookup from the
 *  Manager home page (q) searches the last year. */
export function defaultRecordFilters(today: string, isManager = true, q = ''): RecordFilters {
  const history = q && isManager ? 365 : isManager ? 30 : ADMIN_HISTORY_DAYS
  return { from: addDays(today, -history), to: addDays(today, 30), resourceId: '', q, status: 'ALL' }
}

const offsetFormat = new Intl.DateTimeFormat('en-US', { timeZone: SYDNEY, timeZoneName: 'longOffset' })

/** Start of a Sydney calendar day with its UTC offset, e.g. "2026-11-02T00:00:00+11:00" (handles daylight saving). */
export function sydneyMidnight(ymd: string): string {
  // 14:00 UTC the day before is 00:00 or 01:00 in Sydney on ymd, before any daylight-saving switch that day (2-3 am).
  const instant = new Date(Date.parse(`${ymd}T00:00:00Z`) - 10 * 3600 * 1000)
  const name = offsetFormat.formatToParts(instant).find((part) => part.type === 'timeZoneName')?.value ?? 'GMT+10:00'
  const offset = name === 'GMT' ? '+00:00' : name.replace('GMT', '')
  return `${ymd}T00:00:00${offset}`
}

/** Query string for admin/bookings/ and admin/bookings/export/ (same filters, so the CSV matches the table). */
export function recordQuery(filters: RecordFilters): URLSearchParams {
  const params = new URLSearchParams({ status: filters.status || 'ALL' })
  if (filters.from) params.set('since', sydneyMidnight(filters.from))
  if (filters.to) params.set('until', sydneyMidnight(addDays(filters.to, 1)))
  if (filters.resourceId) params.set('resource_id', filters.resourceId)
  if (filters.q.trim()) params.set('q', filters.q.trim())
  return params
}

/** "Self" when the person booked for themselves, otherwise who made it. */
export function creatorText(booking: Booking): string {
  if (!booking.on_behalf) return 'Self'
  const creator = booking.created_by_user
  return creator ? `${creator.display_name} (${creator.zid})` : 'Staff'
}

/** Attendance column: only approved bookings are checked; "Not yet" until the check-in window has closed. */
export function attendanceText(booking: Booking): string {
  if (booking.status !== 'APPROVED') return '—'
  if (!booking.attendance) return 'Not yet'
  return ATTENDANCE_TEXT[booking.attendance] || 'Not tracked'
}
