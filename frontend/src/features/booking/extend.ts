// 1.24.0 (client, Week 8): extending a booking in progress (POST bookings/{id}/extend/).
import { TZ } from './format.ts'
import type { Booking, Resource } from '../../api/types/index.ts'

/** The person a booking is for, or a Manager, can extend an approved booking while it is in progress. */
export function canExtend(b: Booking, userId: string | undefined, isManager: boolean, now: number): boolean {
  return b.status === 'APPROVED' && !b.additional_hours && !b.long_booking
    && (isManager || b.student_id === userId)
    && Date.parse(b.start) <= now && now < Date.parse(b.end)
}

const localDay = new Intl.DateTimeFormat('en-CA', { timeZone: TZ })
const localClock = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** New end times after the current end, in the resource's time steps, up to closing time and the longest booking.
 *  The server still checks everything else (the time after is free, weekly hours, induction). */
export function extendOptions(b: Booking, resource: Resource, maxMinutes: number): string[] {
  const step = (resource.selection_step_minutes ?? resource.slot_minutes) * 60000
  const start = Date.parse(b.start)
  const day = localDay.format(new Date(start))
  const closing = resource.closing_time.slice(0, 5)
  const options: string[] = []
  for (let end = Date.parse(b.end) + step; end - start <= maxMinutes * 60000; end += step) {
    const date = new Date(end)
    if (localDay.format(date) !== day || localClock.format(date) > closing) break
    options.push(date.toISOString())
  }
  return options
}
