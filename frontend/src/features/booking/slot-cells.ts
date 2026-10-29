import { fmtDateTime, fmtTime } from './format.ts'
import type { Slot } from '../../api/types/index.ts'

/** How one time cell is shown in the slot picker and the day grid. */
export type CellKind = 'free' | 'taken' | 'held' | 'mine' | 'closed'

const OUTSIDE_WINDOW: Slot['reason_code'][] = ['START_TIME_PASSED', 'TOO_SOON', 'TOO_FAR_AHEAD', 'RESOURCE_UNAVAILABLE']

export function kindOf(slot: Slot): CellKind {
  if (OUTSIDE_WINDOW.includes(slot.reason_code)) return 'closed'
  if (slot.requested_by_me) return 'mine'
  if (slot.available) return 'free'
  if (slot.reason_code === 'TEMPORARILY_HELD') return 'held'
  return 'taken'
}

export function cellTitle(slot: Slot, kind: CellKind, minDays: number, maxDays: number): string {
  const when = `${fmtTime(slot.start)} – ${fmtTime(slot.end)}`
  switch (kind) {
    case 'free': return `${when}: available`
    case 'mine': return `${when}: you already have a request here`
    case 'held': return `${when}: awaiting approval for another request${slot.hold_until ? ` (decided by ${fmtDateTime(slot.hold_until)})` : ''}. You can still join the waitlist.`
    case 'taken': return `${when}: booked. You can still join the waitlist.`
    default:
      return `${when}: ${slot.reason_code === 'START_TIME_PASSED' ? 'already passed'
        : slot.reason_code === 'TOO_SOON' ? `too soon (book at least ${minDays} day${minDays === 1 ? '' : 's'} ahead)`
          : slot.reason_code === 'TOO_FAR_AHEAD' ? `too far ahead (at most ${maxDays} days)`
            : slot.reason_code === 'RESOURCE_UNAVAILABLE' ? 'not open for new requests' : 'not bookable'}`
  }
}

// Sprint 3 (1.15.0): red "now" line on today's grid.
/**
 * Where the current time sits across a day's cells, from 0 (start of the first cell) to 1 (end of the last).
 * Returns null when now is outside the shown hours (other days, before opening, after closing), so no line is drawn.
 */
export function nowLineFraction(slots: Pick<Slot, 'start' | 'end'>[], now: number): number | null {
  if (slots.length === 0) return null
  const first = Date.parse(slots[0].start)
  const last = Date.parse(slots[slots.length - 1].end)
  if (!(now > first && now < last)) return null
  return (now - first) / (last - first)
}
