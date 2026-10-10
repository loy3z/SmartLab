import type {
  AuthResponse,
  Availability,
  Booking,
  ListResponse,
  Qualification,
  Requirement,
  Resource,
  User,
} from './types'

const BASE = '/api/v1/'
const TOKEN_KEY = 'access_token'

// Frontend A owns login; this only reads/writes the shared token.
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t: string | null) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY)

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>
  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(BASE + path, { ...init, headers })
  const body = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) {
    const e = body?.error
    throw new ApiError(res.status, e?.code ?? 'UNKNOWN', e?.message ?? res.statusText, e?.details ?? {})
  }
  return body as T
}

const post = <T>(path: string, data: unknown, headers?: HeadersInit) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(data), headers })

export const demoLogin = (zid: string) => post<AuthResponse>('auth/demo-login/', { zid })

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