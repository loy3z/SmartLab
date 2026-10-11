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
}

export type SlotReason =
  | 'START_TIME_PASSED'
  | 'TOO_SOON'
  | 'TOO_FAR_AHEAD'
  | 'BOOKED'
  | 'TEMPORARILY_HELD'
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
}

export type BookingStatus =
  | 'WAITING_QUALIFICATION'
  | 'WAITLISTED'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'EXPIRED'

export interface OutlookSync {
  status: 'DISABLED' | 'NOT_REQUIRED' | 'PENDING' | 'IN_PROGRESS' | 'SYNCED' | 'FAILED'
  action: 'CREATE' | 'UPDATE' | 'DELETE' | null
  web_link: string | null
  last_error: string | null
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
  hold_active: boolean
  blocks_slot: boolean
  /** 1-based place among overlapping waitlisted requests; only meaningful when WAITLISTED. */
  waitlist_position?: number | null
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
}

export interface Qualification {
  id: string
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
  inductions: UserInduction[]
  induction_status: 'VERIFIED' | 'INCOMPLETE'
}