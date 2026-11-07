// 1.24.0 (client, Week 8): extending a booking in progress (POST bookings/{id}/extend/).
// 2026-11-07: the person drags the end on a timeline and a Manager decides; a Manager's own extension applies at once.
import { TZ } from './format.ts'
import type { Booking, Resource, Slot } from '../../api/types/index.ts'

/** The person a booking is for, or a Manager, can extend an approved booking while it is in progress. */
export function canExtend(b: Booking, userId: string | undefined, isManager: boolean, now: number): boolean {
  return b.status === 'APPROVED' && !b.additional_hours && !b.long_booking
    && (isManager || b.student_id === userId)
    && Date.parse(b.start) <= now && now < Date.parse(b.end)
}

/** A later end the person asked for that is still waiting for a Manager (it lapses once that time has passed). */
export function waitingExtension(b: Booking, now: number): string | null {
  return b.extension_end && Date.parse(b.extension_end) > now ? b.extension_end : null
}

const localDay = new Intl.DateTimeFormat('en-CA', { timeZone: TZ })
const localClock = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** Local date (YYYY-MM-DD, Sydney) of a timestamp. */
export const sydneyDate = (iso: string) => localDay.format(new Date(iso))

const stepMs = (resource: Resource) => (resource.selection_step_minutes ?? resource.slot_minutes) * 60000

/** Times from `from` onwards in the resource's steps, up to its closing time on the same local day (both included). */
function stepsToClosing(from: number, resource: Resource): number[] {
  const day = localDay.format(new Date(from))
  const closing = resource.closing_time.slice(0, 5)
  const times: number[] = []
  for (let t = from; localDay.format(new Date(t)) === day && localClock.format(new Date(t)) <= closing; t += stepMs(resource)) times.push(t)
  return times
}

/** New end times after the current one, up to closing time and the longest booking (the server checks the rest). */
export function extendOptions(b: Booking, resource: Resource, maxMinutes: number): string[] {
  const start = Date.parse(b.start)
  return stepsToClosing(Date.parse(b.end), resource).slice(1)
    .filter((t) => t - start <= maxMinutes * 60000)
    .map((t) => new Date(t).toISOString())
}

/** Start of each timeline cell, from the booking's start to closing time. */
export function timelineCells(b: Booking, resource: Resource): string[] {
  const times = stepsToClosing(Date.parse(b.start), resource)
  return times.slice(0, -1).map((t) => new Date(t).toISOString())
}

/** The latest end before someone else's booking or held time (Infinity when the rest of the day is free). */
export function latestEnd(b: Booking, slots: Slot[]): number {
  const end = Date.parse(b.end)
  const blocked = slots.filter((slot) => Date.parse(slot.start) >= end
    && (slot.reason_code === 'BOOKED' || slot.reason_code === 'TEMPORARILY_HELD' || slot.reason_code === 'RESOURCE_UNAVAILABLE'))
  return blocked.length ? Math.min(...blocked.map((slot) => Date.parse(slot.start))) : Infinity
}
