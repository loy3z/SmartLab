export type ResourceKind = 'ROOM' | 'EQUIPMENT'

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
}

export type SlotReason = 'START_TIME_PASSED' | 'BOOKED' | 'TEMPORARILY_HELD' | null

export interface Slot {
  start: string
  end: string
  available: boolean
  reason_code: SlotReason
  hold_until: string | null
  held_by_me: boolean
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
}

export interface ListResponse<T> {
  count: number
  results: T[]
}

export interface AuthResponse {
  access_token: string
  user: { id: string; zid: string; display_name: string; role: string }
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

export interface User {
  id: string
  zid: string
  display_name: string
  role: string
}
