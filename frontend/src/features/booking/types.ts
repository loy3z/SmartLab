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
  date: string
  duration_minutes: number
  timezone: string
  earliest_date: string
  latest_date: string
  min_advance_days: number
  max_advance_days: number
  rooms: { id: string; name: string }[]
  categories: string[]
  count: number
  results: DayOverviewRow[]
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
  resource_id: string
  date: string
  timezone: string
  duration_minutes: number
  slots: Slot[]
  can_request: boolean
  qualification_status: QualificationStatus
  /** Booking window (resource-local dates): starts must fall from earliest_date to latest_date. */
  earliest_date: string
  latest_date: string
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
}

export interface ListResponse<T> {
  count: number
  results: T[]
}

export interface AuthResponse {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  user: User
  mode: 'demo'
}

export interface AuthConfig {
  mode: 'demo' | 'external_provider_required'
  demo_auth_enabled: boolean
  demo_registration_enabled: boolean
  sso_connected: boolean
  token_type: 'Bearer'
  /** Admins and Managers sign in on the staff page with zID + password. */
  staff_sign_in_enabled?: boolean
}

export interface Dashboard {
  bookings: Booking[]
  qualifications: Qualification[]
  counts: Record<BookingStatus, number>
}

export interface Requirement {
  id: string
  name: string
  description: string
  /** Inductions that must be verified and current first (e.g. General before Advanced). */
  prerequisite_ids: string[]
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

export type Role = 'STUDENT' | 'ADMIN' | 'MANAGER'

export interface User {
  id: string
  zid: string
  display_name: string
  role: Role
  university_email: string
  active: boolean
}

export interface UserInduction {
  requirement_id: string
  name: string
  status:
    | 'NOT_SUBMITTED'
    | 'PENDING'
    | 'VERIFIED'
    | 'REJECTED'
    | 'EXPIRED'
  valid_until: string | null
}

export interface ManagedUser extends User {
  /** Admins and Managers are staff accounts; students are never promoted to staff. */
  is_staff: boolean
  /** Staff only: AWAITING_ACTIVATION until they choose a password with the invite code. Null for students. */
  activation_status: 'AWAITING_ACTIVATION' | 'ACTIVATED' | null
  /** Staff only, while awaiting activation: the code the Manager hands over. */
  invite_code: string | null
  inductions: UserInduction[]
  induction_status: 'VERIFIED' | 'INCOMPLETE'
}