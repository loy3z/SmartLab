// Sprint 3 (2026-10-27): moved from the booking feature folder; definitions unchanged.
import type { Role } from './auth'
import type { Booking } from './bookings'
import type { PersonBrief, Resource } from './resources'

export type UnfreezeStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface UnfreezeRequest {
  id: string
  principal_id: string
  reason: string
  created_at: string
  status: UnfreezeStatus
  decided_by: string | null
  decided_at: string | null
  decision_reason: string | null
  person: (PersonBrief & { frozen_until: string | null; booking_frozen: boolean }) | null
  decided_by_user: PersonBrief | null
}

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
  unfreeze_requests: number
  out_of_service: { resource: Resource; affected_bookings: number }[]
  today: Booking[]
  today_count: number
  missed_today: number
  can_decide_urgent: boolean
}
