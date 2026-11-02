// Sprint 3: weekly series helpers.
import type { SeriesOccurrence } from '../../api/types/index.ts'

export const WEEKDAYS: { value: number; short: string; long: string }[] = [
  { value: 1, short: 'Mon', long: 'Monday' },
  { value: 2, short: 'Tue', long: 'Tuesday' },
  { value: 3, short: 'Wed', long: 'Wednesday' },
  { value: 4, short: 'Thu', long: 'Thursday' },
  { value: 5, short: 'Fri', long: 'Friday' },
  { value: 6, short: 'Sat', long: 'Saturday' },
  { value: 7, short: 'Sun', long: 'Sunday' },
]

export const SERIES_REASON_TEXT: Record<string, string> = {
  BOOKING_CONFLICT: 'Already booked or held',
  DUPLICATE_BOOKING: 'This person already has a request then',
  BOOKING_TOO_SOON: 'Too soon (minimum advance days)',
  BOOKING_TOO_FAR_AHEAD: 'Beyond the latest bookable date',
  OUTSIDE_OPENING_HOURS: 'Outside opening hours',
  INVALID_TIME_INCREMENT: 'Not on the time grid',
  DURATION_LIMIT: 'Longer than allowed',
  INVALID_TIME: 'In the past',
  QUALIFICATION_REQUIRED: 'Induction not valid on this date',
  RESOURCE_UNAVAILABLE: 'Resource unavailable',
  ACCOUNT_INACTIVE: 'Account inactive',
}

export function addDaysIso(ymd: string, days: number): string {
  const value = new Date(`${ymd}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}

/** Weekday (1 = Monday ... 7 = Sunday) of a "YYYY-MM-DD" date. */
export function isoWeekday(ymd: string): number {
  const day = new Date(`${ymd}T00:00:00Z`).getUTCDay()
  return day === 0 ? 7 : day
}

/** Dates the staff member must skip: every occurrence the server marked as not bookable. */
export function problemDates(occurrences: SeriesOccurrence[]): string[] {
  return occurrences.filter((item) => !item.available).map((item) => item.date)
}

/** "HH:MM" start times on the resource's grid between opening and closing (exclusive of closing). */
export function startTimes(opening: string, closing: string, slotMinutes: number): string[] {
  const toMinutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5))
  const times: string[] = []
  for (let t = toMinutes(opening); t < toMinutes(closing); t += slotMinutes) {
    times.push(`${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`)
  }
  return times
}
