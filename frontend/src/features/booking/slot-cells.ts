import { fmtDateTime, fmtTime } from './format.ts'
import type { Slot } from './types.ts'

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
