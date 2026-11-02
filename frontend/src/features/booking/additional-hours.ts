import type { Booking } from '../../api/types/index.ts'

export function additionalHoursPriority(booking: Booking): string {
  const review = booking.additional_hours_review
  if (!review) return 'Priority will be checked before approval'
  if (review.priority_group === 'STANDARD') return 'Standard priority'
  return review.priority_reasons.map(reason => reason === 'NO_USE_THIS_WEEK'
    ? 'No recorded lab use this week'
    : 'Active data collection (Manager confirmation required)').join(' · ') || 'Priority'
}

/** The two priority reasons are equal; submission time breaks ties. */
export function compareAdditionalHours(a: Booking, b: Booking): number {
  return Number(b.additional_hours_review?.priority_group === 'PRIORITY') - Number(a.additional_hours_review?.priority_group === 'PRIORITY')
    || a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)
}
