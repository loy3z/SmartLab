// Sprint 3: My Bookings shows a weekly series as one card instead of one card per date.
import type { Booking } from '../../api/types/index.ts'

/** Approval states that still count as live on My Bookings cards (shared by the page and SeriesCard). */
export const ACTIVE = ['WAITING_QUALIFICATION', 'WAITLISTED', 'PENDING_APPROVAL', 'APPROVED']

const SYDNEY = 'Australia/Sydney'
const WEEKDAY_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const weekdayOf = new Intl.DateTimeFormat('en-AU', { weekday: 'short', timeZone: SYDNEY })
const clock = new Intl.DateTimeFormat('en-AU', { timeStyle: 'short', timeZone: SYDNEY }) // "9:00 am", like fmtTime

export type BookingGroup =
  | { kind: 'single'; booking: Booking }
  | { kind: 'series'; seriesId: string; bookings: Booking[] } // bookings sorted by start time

/**
 * One entry per single booking and one per weekly series, keeping the list's order: a series appears where its
 * first date appears in the list (the list is newest request first).
 */
export function groupBookings(bookings: Booking[]): BookingGroup[] {
  const groups: BookingGroup[] = []
  const series = new Map<string, Booking[]>()
  for (const booking of bookings) {
    if (!booking.series_id) {
      groups.push({ kind: 'single', booking })
      continue
    }
    const dates = series.get(booking.series_id)
    if (dates) {
      dates.push(booking)
    } else {
      const created = [booking]
      series.set(booking.series_id, created)
      groups.push({ kind: 'series', seriesId: booking.series_id, bookings: created })
    }
  }
  for (const group of groups) {
    if (group.kind === 'series') group.bookings.sort((a, b) => Date.parse(a.start) - Date.parse(b.start))
  }
  return groups
}

export interface SeriesSummary {
  /** "Every Mon, Wed · 9:00 am – 10:00 am"; "(times vary)" when a Manager moved some dates. */
  pattern: string
  firstStart: string
  lastStart: string
  total: number
  /** Approved dates that have not ended yet. */
  remaining: number
  cancelled: number
  /** The next approved date that has not ended (it may be happening now). */
  next: Booking | null
}

/** Facts shown on a series card. `now` is milliseconds since 1970. */
export function seriesSummary(bookings: Booking[], now: number): SeriesSummary {
  const sorted = [...bookings].sort((a, b) => Date.parse(a.start) - Date.parse(b.start))
  const upcoming = sorted.filter((item) => item.status === 'APPROVED' && Date.parse(item.end) > now)
  const days = new Set(sorted.map((item) => weekdayOf.format(new Date(item.start))))
  const ordered = WEEKDAY_ORDER.filter((day) => days.has(day))
  const ranges = new Set(sorted.map((item) => `${clock.format(new Date(item.start))} – ${clock.format(new Date(item.end))}`))
  const reference = upcoming[0] ?? sorted[0]
  const range = reference ? `${clock.format(new Date(reference.start))} – ${clock.format(new Date(reference.end))}` : ''
  return {
    pattern: `Every ${ordered.join(', ')} · ${range}${ranges.size > 1 ? ' (times vary)' : ''}`,
    firstStart: sorted[0]?.start ?? '',
    lastStart: sorted[sorted.length - 1]?.start ?? '',
    total: sorted.length,
    remaining: upcoming.length,
    cancelled: sorted.filter((item) => item.status === 'CANCELLED').length,
    next: upcoming[0] ?? null,
  }
}
