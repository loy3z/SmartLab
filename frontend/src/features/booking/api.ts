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
export const getDashboard = () => request<Dashboard>('dashboard/')
export const downloadQualification = (id: string) => requestBlob(`qualifications/${id}/file/`)

export function listResources(params: { kind?: string; q?: string }) {
  const qs = new URLSearchParams()
  if (params.kind) qs.set('kind', params.kind)
  if (params.q) qs.set('q', params.q)
  return request<ListResponse<Resource>>(`resources/?${qs}`)
}

export const getAvailability = (id: string, date: string, durationMinutes: number) =>
  request<Availability>(
    `resources/${id}/availability/?date=${date}&duration_minutes=${durationMinutes}`,
  )

export const createBooking = (
  data: { resource_id: string; start: string; end: string; purpose: string },
  idempotencyKey: string,
) => post<Booking>('bookings/', data, { 'Idempotency-Key': idempotencyKey })

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
  status:
    | 'WAITING_QUALIFICATION'
    | 'WAITLISTED'
    | 'PENDING_APPROVAL' = 'WAITLISTED',
) {
  return request<ListResponse<Booking>>(
    `admin/bookings/?status=${status}`,
  )
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
  return request<ListResponse<User>>('admin/users/')
}

export function updateUserRole(
  userId: string,
  role: 'STUDENT' | 'ADMIN',
) {
  return request<User>(`admin/users/${userId}/`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  })
}
