import type {
  AuthConfig,
  AuthResponse,
  Availability,
  Booking,
  Dashboard,
  ListResponse,
  Qualification,
  Requirement,
  Resource,
  User,
  ManagedUser,
  ResourceStatus,
  PersonBrief,
  CalendarCheck,
  CalendarSyncStatus,
  DayOverview,
  DayOverviewQuery,
} from './types'
import { request, requestBlob } from '../../lib/api-client'
export { ApiError, getToken, setToken } from '../../lib/api-client'

const post = <T>(path: string, data: unknown, headers?: HeadersInit) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(data), headers })

export const getAuthConfig = () => request<AuthConfig>('auth/config/', {}, { authenticated: false })
export const demoLogin = (zid: string) => request<AuthResponse>('auth/demo-login/', {
  method: 'POST', body: JSON.stringify({ zid }),
}, { authenticated: false })
export const demoRegister = (data: { zid: string; display_name: string; university_email: string }) =>
  request<AuthResponse>('auth/demo-register/', { method: 'POST', body: JSON.stringify(data) }, { authenticated: false })
/** Staff sign-in page (Admins and Managers). Students use university sign-in. */
export const staffSignIn = (zid: string, password: string) =>
  request<AuthResponse>('auth/staff-sign-in/', { method: 'POST', body: JSON.stringify({ zid, password }) }, { authenticated: false })
/** First staff sign-in: the invite code from a Manager plus a new password. */
export const staffActivate = (data: { zid: string; invite_code: string; password: string }) =>
  request<AuthResponse>('auth/staff-activate/', { method: 'POST', body: JSON.stringify(data) }, { authenticated: false })
export const getDashboard = () => request<Dashboard>('dashboard/')
export const downloadQualification = (id: string) => requestBlob(`qualifications/${id}/file/`)

export function listResources(params: { kind?: string; q?: string }) {
  const qs = new URLSearchParams()
  if (params.kind) qs.set('kind', params.kind)
  if (params.q) qs.set('q', params.q)
  return request<ListResponse<Resource>>(`resources/?${qs}`)
}

export function getAvailability(
  id: string,
  date: string,
  durationMinutes: number,
  excludeBookingId?: string,
  options: { forZid?: string; urgent?: boolean } = {},
) {
  const qs = new URLSearchParams({ date, duration_minutes: String(durationMinutes) })
  if (excludeBookingId) qs.set('exclude_booking_id', excludeBookingId)
  if (options.forZid) qs.set('for_zid', options.forZid)
  if (options.urgent) qs.set('urgent', 'true')
  return request<Availability>(`resources/${id}/availability/?${qs}`)
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

export const createBooking = (data: BookingRequest, idempotencyKey: string) =>
  post<Booking>('bookings/', data, { 'Idempotency-Key': idempotencyKey })

/** Admin/Manager: check whom you are booking for. */
export const lookupPerson = (zid: string) =>
  request<PersonBrief>(`people/lookup/?${new URLSearchParams({ zid })}`)

export const listBookings = () => request<ListResponse<Booking>>('bookings/')

export const cancelBooking = (id: string) => post<Booking>(`bookings/${id}/cancel/`, {})

export const rescheduleBooking = (id: string, start: string, end: string) =>
  post<Booking>(`bookings/${id}/reschedule/`, { start, end })

export const getMe = () => request<User>('auth/me/')
export const listRequirements = () => request<ListResponse<Requirement>>('qualification-requirements/')
export const listQualifications = () => request<ListResponse<Qualification>>('qualifications/')

export function submitQualification(
  requirementId: string,
  title: string,
  notes: string,
  file: File,
) {
  const formData = new FormData()

  formData.append('requirement_id', requirementId)
  formData.append('title', title)
  formData.append('notes', notes)
  formData.append('file', file)

  return request<Qualification>('qualifications/', {
    method: 'POST',
    body: formData,
  })
}
export function listAdminQualifications(
  status: 'PENDING' | 'VERIFIED' | 'REJECTED' = 'PENDING',
) {
  return request<ListResponse<Qualification>>(
    `admin/qualifications/?status=${status}`,
  )
}


export function reviewQualification(
  submissionId: string,
  decision: 'VERIFIED' | 'REJECTED',
  reason: string = '',
) {
  return post<{
    submission: Qualification
    updated_bookings: Booking[]
  }>(`admin/qualifications/${submissionId}/review/`, {
    decision,
    reason,
  })
}

export function listApprovedBookings() {
  return request<ListResponse<Booking>>(
    'admin/bookings/?status=APPROVED',
  )
}
export function listAdminBookings(
  status: 'WAITLISTED' | 'PENDING_APPROVAL' = 'PENDING_APPROVAL',
) {
  return request<ListResponse<Booking>>(
    `admin/bookings/?status=${status}`,
  )
}

/** Admin/Manager: every booking of one student (all statuses). */
export function listStudentBookings(studentId: string) {
  const params = new URLSearchParams({ status: 'ALL', student_id: studentId })
  return request<ListResponse<Booking>>(`admin/bookings/?${params}`)
}

export function reviewBooking(
  bookingId: string,
  decision: 'APPROVED' | 'REJECTED',
  reason: string = '',
) {
  return post<Booking>(
    `admin/bookings/${bookingId}/review/`,
    { decision, reason },
  )
}

export function listManagerUsers() {
  return request<ListResponse<ManagedUser>>('admin/users/')
}

/** Manager only: deactivate (sign-in blocked) or reactivate an account. Roles never change. */
export function setUserActive(userId: string, active: boolean) {
  return request<ManagedUser>(`admin/users/${userId}/`, {
    method: 'PATCH',
    body: JSON.stringify({ active }),
  })
}

/** Manager only: clear a staff member's password and issue a new invite code. */
export const resetStaffAccess = (userId: string) => post<ManagedUser>(`admin/users/${userId}/reset-access/`, {})

/** Manager only ("Add staff"): creates a new Admin or Manager account. */
export function createStaff(data: { zid: string; display_name: string; university_email: string; role: 'ADMIN' | 'MANAGER' }) {
  return post<ManagedUser>('admin/users/staff/', data)
}

export function downloadAllBookings() {
  return requestBlob('admin/bookings/export/?status=ALL')
}

export function downloadUserBookings(studentId: string) {
  const params = new URLSearchParams({
    status: 'ALL',
    student_id: studentId,
  })

  return requestBlob(`admin/bookings/export/?${params.toString()}`)
}

export function updateResourceStatus(
  resourceId: string,
  status: ResourceStatus,
  reason: string,
) {
  return request<{
    resource: Resource
    affected_bookings: Booking[]
  }>(`admin/resources/${resourceId}/status/`, {
    method: 'PATCH',
    body: JSON.stringify({ status, reason }),
  })
}

// Calendar Sync (Admin and Manager). Reading the status never calls Microsoft; the actions do.
export const getCalendarSync = () => request<CalendarSyncStatus>('admin/outlook/')
export const checkCalendarConnection = () => post<CalendarCheck>('admin/outlook/check/', {})
export const processCalendarSync = () => post<{ processed_count: number }>('admin/outlook/process/', { limit: 5 })
export const retryCalendarSync = (bookingId: string) => post<Booking>(`admin/bookings/${bookingId}/outlook-retry/`, {})

/** Booking page day grid: every matching resource's free and taken times on one day. */
export function getDayOverview(query: DayOverviewQuery) {
  const qs = new URLSearchParams({ date: query.date, duration_minutes: String(query.duration_minutes) })
  if (query.kind) qs.set('kind', query.kind)
  if (query.room_id) qs.set('room_id', query.room_id)
  if (query.category) qs.set('category', query.category)
  if (query.q) qs.set('q', query.q)
  if (query.bookable_only) qs.set('bookable_only', 'true')
  if (query.free_at) qs.set('free_at', query.free_at)
  return request<DayOverview>(`resources/day-overview/?${qs}`)
}
