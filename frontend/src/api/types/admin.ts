// Sprint 3 (2026-10-27): moved from the booking feature folder; definitions unchanged.
import type { Role } from './auth'
import type { Booking } from './bookings'
import type { Resource } from './resources'

/** Sprint 3 (1.16.0): the staff "Today" page (GET admin/overview/). */
export interface StaffOverview {
  role: Role
  pending_inductions: number
  pending_bookings: number
  urgent_requests: number
  waitlisted: number
  changes_waiting: number
  due_soon: Booking[]
  due_soon_hours: number
  out_of_service: { resource: Resource; affected_bookings: number }[]
  today: Booking[]
  today_count: number
  missed_today: number
  can_decide_urgent: boolean
  additional_hours_requests?: number
  additional_hours_ready?: number
  can_decide_additional_hours?: boolean
  long_booking_requests?: number
  can_decide_long_bookings?: boolean
}
