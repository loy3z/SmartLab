// Sprint 3 (2026-10-27): moved from the booking feature folder; definitions unchanged.
import type { PersonBrief, Qualification } from './resources'

export type BookingStatus =
  | 'WAITING_QUALIFICATION'
  | 'WAITLISTED'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'EXPIRED'

export type CalendarSyncState = 'DISABLED' | 'NOT_REQUIRED' | 'PENDING' | 'IN_PROGRESS' | 'SYNCED' | 'FAILED'

export interface OutlookSync {
  status: CalendarSyncState
  action: 'CREATE' | 'UPDATE' | 'DELETE' | null
  web_link: string | null
  last_error: string | null
}

/** One row of the staff Calendar Sync page (GET admin/outlook/). */
export interface CalendarSyncItem {
  booking_id: string
  booking_status: BookingStatus
  start: string
  end: string
  urgent: boolean
  resource: { id: string; name: string | null; location: string | null }
  booked_for: { zid: string; display_name: string } | null
  booked_by: { zid: string; display_name: string } | null
  /** Whether the person gets a meeting invitation (OUTLOOK_INVITE_MODE). */
  invited: boolean
  sync: {
    status: Exclude<CalendarSyncState, 'DISABLED' | 'NOT_REQUIRED'>
    action: 'CREATE' | 'UPDATE' | 'DELETE'
    attempts: number
    last_error: string | null
    next_attempt_at: string | null
    last_success_at: string | null
    web_link: string | null
  }
}

export interface CalendarCheck {
  at: string
  ok: boolean
  /** e.g. TOKEN_EXPIRED, OUTLOOK_LOGIN_EXPIRED, OUTLOOK_NOT_CONFIGURED, GRAPH_HTTP_403. */
  code: string | null
  mode: string
  calendar_name: string | null
  owner: string | null
}

export interface CalendarSyncStatus {
  enabled: boolean
  configured: boolean
  mode: string
  direction: 'system_to_outlook'
  invite_mode: 'none' | 'allowlist' | 'all' | null
  last_check: CalendarCheck | null
  summary: { total: number; synced: number; pending: number; failed: number }
  items: CalendarSyncItem[]
}

export interface Booking {
  id: string
  student_id: string
  resource_id: string
  start: string
  end: string
  purpose: string
  created_at: string
  status: BookingStatus
  reason_code: string | null
  decision_reason: string | null
  revision: number
  outlook_sync?: OutlookSync
  hold_until: string | null
  /** End of the Admin review window for a pending request; afterwards the system decides. */
  review_due_at: string | null
  /** Admin/Manager id, or "SYSTEM" for an automatic decision. */
  reviewed_by: string | null
  hold_active: boolean
  blocks_slot: boolean
  /** 1-based place among overlapping waitlisted requests; only meaningful when WAITLISTED. */
  waitlist_position?: number | null
  /** Admin/Manager lists only: who the booking is for. */
  student?: { id: string; zid: string; display_name: string; university_email: string } | null
  resource_name?: string | null
  /** Who created the request; differs from the person it is for when staff booked on their behalf. */
  created_by?: string | null
  booked_for?: PersonBrief | null
  created_by_user?: PersonBrief | null
  on_behalf?: boolean
  /** Urgent request: inside the minimum advance window; only a Manager can decide it. */
  urgent?: boolean
  urgent_reason?: string | null
  long_booking?: boolean
  long_booking_reason?: string | null
  /** Separate request for unused capacity beyond the normal weekly allowance. */
  additional_hours?: boolean
  additional_hours_reason?: string | null
  active_data_collection?: boolean
  data_collection_reason?: string | null
  additional_hours_review?: AdditionalHoursReview | null
  /** Sprint 3: weekly series made by staff; null for single bookings. */
  series_id?: string | null
  /** Sprint 3: CHECKED_IN, NO_SHOW (missed), EXCUSED (resource unavailable), NOT_TRACKED, or null (not yet). */
  attendance?: Attendance | null
  checked_in_at?: string | null
  /** True while the "I'm here" check-in button should show. */
  check_in_open?: boolean
  check_in_opens_at?: string | null
  check_in_closes_at?: string | null
  /** Sprint 3 (1.16.0): on a change request, the approved booking it would replace (cancelled once this is approved). */
  replaces_id?: string | null
  replaces_booking?: BookingTimeRef | null
  /** Sprint 3 (1.16.0): on an approved booking, its change request that is still waiting (pending or waitlisted). */
  open_change?: BookingTimeRef | null
}

export interface AdditionalHoursReview {
  approval_opens_at: string
  approval_window_hours: number
  priority_group: 'PRIORITY' | 'STANDARD'
  priority_reasons: ('NO_USE_THIS_WEEK' | 'ACTIVE_DATA_COLLECTION')[]
  queue_position: number | null
  /** Business eligibility only; role and self-review restrictions still apply. */
  can_approve: boolean
  blocker_code: string | null
  blocker_message: string | null
}

export interface AdditionalHoursRequest {
  resource_id: string
  start: string
  end: string
  purpose: string
  additional_hours_reason: string
  active_data_collection: boolean
  data_collection_reason?: string
  on_behalf_of_zid?: string
}

export interface LongBookingRequest {
  resource_id: string
  start: string
  end: string
  purpose: string
  long_booking_reason: string
  on_behalf_of_zid?: string
}

/** Sprint 3 (1.16.0): the time and status of a linked booking (change requests). */
export interface BookingTimeRef {
  id: string
  start: string
  end: string
  status: BookingStatus
}

// Sprint 3: check-in, notifications, calendar link, booking freeze, weekly series ----------------------------

export type Attendance = 'CHECKED_IN' | 'NO_SHOW' | 'EXCUSED' | 'NOT_TRACKED'

export interface SeriesPlan {
  resource_id: string
  /** ISO weekdays: 1 = Monday ... 7 = Sunday. */
  weekdays: number[]
  /** Local "HH:MM". */
  start_time: string
  duration_minutes: number
  first_date: string
  last_date: string
  on_behalf_of_zid?: string
}

export interface SeriesOccurrence {
  date: string
  start: string
  end: string
  available: boolean
  reason_code: string | null
  message: string | null
}

export interface SeriesPreview {
  resource_id: string
  booking_for: PersonBrief
  weekdays: number[]
  occurrences: SeriesOccurrence[]
  available_count: number
}

export interface BookingSeries {
  id: string
  student_id: string
  created_by: string
  resource_id: string
  weekdays: number[]
  start_time: string
  duration_minutes: number
  first_date: string
  last_date: string
  purpose: string
  created_at: string
  bookings: Booking[]
}

export interface Dashboard {
  bookings: Booking[]
  qualifications: Qualification[]
  counts: Record<BookingStatus, number>
}

export interface BookingRequest {
  resource_id: string
  start: string
  end: string
  purpose: string
  /** Admin/Manager only: the zID of the person the booking is for. */
  on_behalf_of_zid?: string
  urgent?: boolean
  urgent_reason?: string
}
