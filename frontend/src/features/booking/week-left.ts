// 2026-11-10 (U1): the booking window says how many hours are left in the week being booked.
import type { Availability } from '../../api/types/index.ts'

/** Hours left of the weekly allowance in the week of the chosen day; empty when the allowance does not apply. */
export function weekLeftText(d: Partial<Availability> | null): string {
  if (!d?.week_hours || d.manager_override || d.test_bypass || d.additional_hours || d.long_booking) return ''
  const { week_start, used_hours, limit_hours } = d.week_hours
  const monday = new Date(`${week_start}T00:00:00Z`).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', timeZone: 'UTC' })
  return `Week of ${monday}: ${Math.max(0, limit_hours - used_hours)} h left of your ${limit_hours} h.`
}
