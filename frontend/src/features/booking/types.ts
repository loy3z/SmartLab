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
  /** Sprint 3 (1.16.0): rooms only, how many people fit (null = not given). */
  capacity?: number | null
  /** Sprint 3 (1.16.0): "label: value" lines a Manager adds (model, floor, specs…). */
  details?: ResourceDetail[]
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
  test_bypass?: boolean
  max_booking_minutes?: number
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
  /** Sprint 3: set while the person's booking is frozen after missed check-ins. */
  frozen_until?: string | null
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

/** Sprint 3 (1.16.0): the time and status of a linked booking (change requests). */
export interface BookingTimeRef {
  id: string
  start: string
  end: string
  status: BookingStatus
}

// Sprint 3: check-in, notifications, calendar link, booking freeze, weekly series ----------------------------

export type Attendance = 'CHECKED_IN' | 'NO_SHOW' | 'EXCUSED' | 'NOT_TRACKED'

export interface AppNotification {
  id: string
  recipient_id: string
  kind: string
  title: string
  body: string
  created_at: string
  /** App page to open, e.g. "/bookings". */
  link: string | null
  booking_id: string | null
  read_at: string | null
}

export interface NotificationList {
  count: number
  unread_count: number
  results: AppNotification[]
}

/** Sprint 3 (1.19.0): independent delivery choices; missing preferences default to both channels on. */
export interface NotificationPreference {
  category: string
  in_app: boolean
  email: boolean
}
/** Sprint 3 (1.19.0): attributed home-page announcement, separate from personal notifications. */
export interface Announcement {
  id: string; title: string; body: string; kind: 'MANUAL' | 'RESOURCE_STATUS'; resource_id: string | null
  created_by: string; author_role: 'ADMIN' | 'MANAGER'; author: { id: string; display_name: string; role: 'ADMIN' | 'MANAGER' }
  created_at: string; updated_at: string | null; expires_at: string | null; removed_at: string | null
  expected_back: string | null; active: boolean
}

export interface CalendarLink {
  /** Relative path of the subscription feed; prefix with the site address. */
  path: string
  created_at: string
}

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

export interface FrozenUser extends User {
  pending_request: UnfreezeRequest | null
}

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
  test_console_enabled?: boolean
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

/** Sprint 3 (1.16.0): the lab's contact details (GET/PATCH site/contact/); empty fields are not shown. */
export interface SiteContact {
  email: string
  phone: string
  hours: string
  note: string
  updated_at?: string | null
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
  test_account?: boolean
  bypass_booking_rules?: boolean
  id: string
  zid: string
  display_name: string
  role: Role
  university_email: string
  active: boolean
  /** Sprint 3: missed check-ins since the last freeze. */
  no_show_count?: number
  frozen_until?: string | null
  /** True while booking is frozen (frozen_until is in the future). */
  booking_frozen?: boolean
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

/** A future booking that no longer fits a resource's new rules (it is kept until a Manager acts). */
export interface BookingOutsideRules extends Booking {
  problem: string
}

export interface ResourceUpdateResult {
  resource: Resource
  bookings_outside_rules: BookingOutsideRules[]
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
