// Sprint 3 (2026-10-27): moved from the booking feature folder; definitions unchanged.
import type { Role } from './auth'
import type { Booking } from './bookings'

export type ResourceKind = 'ROOM' | 'EQUIPMENT'

export type ResourceStatus = 'AVAILABLE' | 'MAINTENANCE' | 'CLOSED'

export interface Resource {
  id: string
  name: string
  kind: ResourceKind
  location: string
  description: string
  active: boolean
  required_qualification_id: string | null
  slot_minutes: number
  max_booking_minutes: number
  /** Fair-use unit and effective cap for an ordinary request. */
  booking_slot_minutes?: number
  max_booking_slots?: number
  selection_step_minutes?: number
  effective_max_booking_minutes?: number
  opening_time: string
  closing_time: string
  timezone: string
  pending_hold_minutes: number
  status: ResourceStatus
  status_reason: string | null
  /** Equipment: the room it is kept in. Rooms: null. */
  room_id: string | null
  /** Equipment type for the booking page filter, e.g. "Microscopy". Rooms: null. */
  category?: string | null
  /** Sprint 3 (1.16.0): rooms only, how many people fit (null = not given). */
  capacity?: number | null
  /** Sprint 3 (1.16.0): "label: value" lines a Manager adds (model, floor, specs…). */
  details?: ResourceDetail[]
}

/** 2026-11-07 (client, Week 8): what only Managers see about a resource (GET/PATCH admin/resources/{id}/internal/). */
export interface ResourceInternalInput {
  owner: string
  asset_number: string
  provided_by: string
  specifications: string
}

export interface ResourceInternalInfo extends ResourceInternalInput {
  resource_id: string
  updated_at: string | null
  updated_by: string | null
}

/** Sprint 3 (1.16.0): one "label: value" line on a resource. */
export interface ResourceDetail {
  label: string
  value: string
}

/** One resource's row in the booking page day grid (GET resources/day-overview/). */
export interface DayOverviewRow {
  resource: Resource
  room_name: string | null
  can_request: boolean
  qualification_status: QualificationStatus
  resource_status: ResourceStatus
  status_reason: string | null
  slots: Slot[]
}

export interface DayOverview {
  test_bypass?: boolean
  manager_override?: boolean // 1.24.0: a Manager's window starts today with no last date
  date: string
  duration_minutes: number
  timezone: string
  earliest_date: string
  latest_date: string | null
  min_advance_days: number
  max_advance_days: number
  rooms: { id: string; name: string }[]
  categories: string[]
  count: number
  results: DayOverviewRow[]
  /** Sprint 3 (1.16.0): resources left out because they cannot be booked for this length. */
  too_long?: number
  /** Sprint 3 (1.16.0): rows hidden by "only what I can book", counted by reason (resource or induction status). */
  not_bookable?: Record<string, number>
}

export interface DayOverviewQuery {
  date: string
  duration_minutes: number
  kind?: ResourceKind
  room_id?: string
  category?: string
  q?: string
  bookable_only?: boolean
  /** Local "HH:MM": only resources free for the whole duration from then. */
  free_at?: string
}

export type SlotReason =
  | 'START_TIME_PASSED'
  | 'TOO_SOON'
  | 'TOO_FAR_AHEAD'
  | 'BOOKED'
  | 'TEMPORARILY_HELD'
  | 'RESOURCE_UNAVAILABLE'
  | null

export interface Slot {
  start: string
  end: string
  available: boolean
  reason_code: SlotReason
  hold_until: string | null
  held_by_me: boolean
  /** This user already has an overlapping active request for the resource. */
  requested_by_me: boolean
}

export type QualificationStatus =
  | 'NOT_CONFIGURED'
  | 'NOT_SUBMITTED'
  | 'PENDING'
  | 'VERIFIED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'EXPIRES_BEFORE_END'
  /** A prerequisite induction (e.g. General for Advanced) is not verified and current. */
  | 'PREREQUISITE_REQUIRED'

export interface Availability {
  long_booking?: boolean
  normal_max_booking_minutes?: number
  min_booking_minutes?: number
  additional_hours?: boolean
  additional_hours_approval_window_hours?: number
  test_bypass?: boolean
  /** 1.24.0: a Manager overrides the booking window, induction and limits; only free times can be booked. */
  manager_override?: boolean
  max_booking_minutes?: number
  booking_slot_minutes?: number
  max_booking_slots?: number
  selection_step_minutes?: number
  resource_id: string
  date: string
  timezone: string
  duration_minutes: number
  slots: Slot[]
  can_request: boolean
  qualification_status: QualificationStatus
  /** Booking window (resource-local dates): starts must fall from earliest_date to latest_date. */
  earliest_date: string
  latest_date: string | null
  min_advance_days: number
  max_advance_days: number
  resource_status?: ResourceStatus
  status_reason?: string | null
  /** The resource's admin review window in minutes. */
  review_window_minutes?: number
  /** Set when qualification_status is PREREQUISITE_REQUIRED. */
  missing_prerequisite_id?: string | null
  /** Whose eligibility and requests these results describe (the signed-in user, or for_zid for staff). */
  booking_for?: PersonBrief
  /** Urgent view: times inside the minimum advance window count as available. */
  urgent?: boolean
}

export interface PersonBrief {
  id: string
  zid: string
  display_name: string
  role: Role
}

export interface Requirement {
  id: string
  name: string
  description: string
  /** Inductions that must be verified and current first (e.g. General before Advanced). */
  prerequisite_ids: string[]
  /** Sprint 3 (1.16.0): guidance a Manager writes (empty = not written yet). */
  how_to_complete?: string
  accepted_evidence?: string
  reviewer?: string
  contact?: string
}

/** Sprint 3 (1.16.0): fields a Manager sends when adding or editing an induction. */
export interface RequirementInput {
  name: string
  description: string
  how_to_complete: string
  accepted_evidence: string
  reviewer: string
  contact: string
}


export interface Qualification {
  id: string
  /** Admin/Manager lists only: whose evidence this is. */
  student?: { id: string; zid: string; display_name: string; university_email: string } | null
  student_id: string
  requirement_id: string
  title: string
  notes: string
  file_id: string
  file_url: string
  submitted_at: string
  status: 'PENDING' | 'VERIFIED' | 'REJECTED'
  effective_status: 'PENDING' | 'VERIFIED' | 'REJECTED' | 'EXPIRED'
  reviewed_by: string | null
  reviewed_at: string | null
  rejection_reason: string | null
  valid_until: string | null
}

// Sprint 3: resource setup (Manager) ------------------------------------------------------------------------

/** Fields a Manager fills in to add or edit a room or equipment. Times are "HH:MM". */
export interface ResourceInput {
  name: string
  location: string
  description: string
  required_qualification_id: string
  room_id: string | null
  category: string | null
  slot_minutes: number
  max_booking_minutes: number
  opening_time: string
  closing_time: string
  pending_hold_minutes: number
  /** Sprint 3 (1.16.0) */
  capacity: number | null
  details: ResourceDetail[]
}


export interface ResourceUpdateResult {
  resource: Resource
  bookings_outside_rules: BookingOutsideRules[]
}


/** A future booking that no longer fits a resource's new rules (it is kept until a Manager acts). */
export interface BookingOutsideRules extends Booking {
  problem: string
}

// Sprint 3: usage report (Manager) ---------------------------------------------------------------------------

export interface UsageFigures {
  approved: number
  booked_hours: number
  open_hours: number
  /** booked_hours / open_hours, 0-1; null when the resource has no opening hours in the range */
  utilisation: number | null
  checked_in: number
  no_show: number
  excused: number
  not_tracked: number
  /** checked_in / (checked_in + no_show); null until a booking has been counted */
  attendance_rate: number | null
  cancelled: number
  rejected: number
}

export interface UsageRow extends UsageFigures {
  resource_id: string
  name: string
  kind: ResourceKind
  category: string | null
  room_name: string | null
  active: boolean
}

export interface UsageReport {
  first_date: string
  last_date: string
  days: number
  results: UsageRow[]
  totals: UsageFigures
}
