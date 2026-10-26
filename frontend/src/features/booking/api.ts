import type { Announcement } from './types' // Sprint 3 (1.19.0)
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
  NotificationList,
  AppNotification,
  NotificationPreference,
  CalendarLink,
  UnfreezeRequest,
  FrozenUser,
  SeriesPlan,
  SeriesPreview,
  BookingSeries,
  ResourceKind,
  ResourceInput,
  ResourceUpdateResult,
  UsageReport,
  RequirementInput, SiteContact, StaffOverview, // Sprint 3 (1.16.0)
} from './types'
import { request, requestBlob } from '../../lib/api-client'
export { ApiError, getToken, setToken } from '../../lib/api-client'

const post = <T>(path: string, data: unknown, headers?: HeadersInit) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(data), headers })

export const getAuthConfig = () => request<AuthConfig>('auth/config/', {}, { authenticated: false })
export const testLogin = (loginId: string) => request<AuthResponse>('auth/test-login/', {
  method: 'POST', body: JSON.stringify({ login_id: loginId }),
}, { authenticated: false })
export const changeTestSession = (role: User['role'], bypass: boolean) => request<AuthResponse>('auth/test-session/', {
  method: 'POST', body: JSON.stringify({ role, bypass_booking_rules: bypass }),
})
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

/** Sprint 3 (1.16.0): the person a booking is for asks for a new time; returns the new request (the old booking stays until it is approved). */
export const requestTimeChange = (id: string, start: string, end: string) =>
  post<Booking>(`bookings/${id}/change/`, { start, end })

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

// Sprint 3 (Booking Records, Admin and Manager): the list and its CSV take the same filters
// (status, since, until, resource_id, q = part of a zID or name).
export function listBookingRecords(params: URLSearchParams) {
  return request<ListResponse<Booking>>(`admin/bookings/?${params.toString()}`)
}

export function downloadBookingRecords(params: URLSearchParams) {
  return requestBlob(`admin/bookings/export/?${params.toString()}`)
}

export function updateResourceStatus(
  resourceId: string,
  status: ResourceStatus,
  reason: string,
  expected_back?: string | null, // Sprint 3 (1.19.0)
) {
  return request<{
    resource: Resource
    affected_bookings: Booking[]
  }>(`admin/resources/${resourceId}/status/`, {
    method: 'PATCH',
    body: JSON.stringify({ status, reason, ...(expected_back !== undefined ? { expected_back } : {}) }),
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

// Sprint 3: calendar subscription link ---------------------------------------------------------------------------------
export const getCalendarLink = () => request<CalendarLink>('calendar/link/')
export const resetCalendarLink = () => post<CalendarLink>('calendar/link/reset/', {})

// Sprint 3: notifications ---------------------------------------------------------------------------------------------
export function listNotifications(options: { unread?: boolean; limit?: number } = {}) {
  const qs = new URLSearchParams()
  if (options.unread) qs.set('unread', 'true')
  if (options.limit) qs.set('limit', String(options.limit))
  return request<NotificationList>(`notifications/?${qs}`)
}
export const markNotificationRead = (id: string) => post<AppNotification>(`notifications/${id}/read/`, {})
export const markAllNotificationsRead = () => post<{ updated: number }>('notifications/read-all/', {})

// Sprint 3 (2026-10-25): notification category choices.
export const getNotificationPreferences = () =>
  request<{ results: NotificationPreference[]; email_available: boolean }>('notifications/preferences/')
export const saveNotificationPreferences = (preferences: Record<string, Partial<Pick<NotificationPreference, 'in_app' | 'email'>>>) =>
  request<{ results: NotificationPreference[]; email_available: boolean }>('notifications/preferences/', {
    method: 'PUT', body: JSON.stringify({ preferences }),
  })

// Sprint 3: check-in and booking freeze ---------------------------------------------------------------------------------
export const checkIn = (bookingId: string) => post<Booking>(`bookings/${bookingId}/check-in/`, {})
export const listMyUnfreezeRequests = () => request<ListResponse<UnfreezeRequest>>('account/unfreeze-requests/')
export const requestUnfreeze = (reason: string) => post<UnfreezeRequest>('account/unfreeze-requests/', { reason })
export const listFrozenUsers = () => request<ListResponse<FrozenUser>>('admin/frozen-users/')
export function listUnfreezeRequests(status?: 'PENDING' | 'APPROVED' | 'REJECTED') {
  const qs = new URLSearchParams()
  if (status) qs.set('status', status)
  return request<ListResponse<UnfreezeRequest>>(`admin/unfreeze-requests/?${qs}`)
}
export const reviewUnfreeze = (id: string, decision: 'APPROVED' | 'REJECTED', reason = '') =>
  post<UnfreezeRequest>(`admin/unfreeze-requests/${id}/review/`, { decision, reason })
export const unfreezeUser = (userId: string, reason = '') => post<User>(`admin/users/${userId}/unfreeze/`, { reason })

// Sprint 3: weekly series (staff) ---------------------------------------------------------------------------------------
export const previewSeries = (plan: SeriesPlan) => post<SeriesPreview>('bookings/series/preview/', plan)
export const createSeries = (plan: SeriesPlan & { purpose: string; skip_dates: string[] }) =>
  post<BookingSeries>('bookings/series/', plan)
export const getSeries = (id: string) => request<BookingSeries>(`bookings/series/${id}/`)
export const cancelSeries = (id: string) => post<BookingSeries>(`bookings/series/${id}/cancel/`, {})

// Sprint 3: resource setup (Manager) ------------------------------------------------------------------------
export const listAllResources = () => request<ListResponse<Resource>>('admin/resources/')
export const createResource = (kind: ResourceKind, fields: ResourceInput) =>
  post<Resource>('admin/resources/', { kind, ...fields })
export const updateResource = (resourceId: string, fields: Partial<ResourceInput>) =>
  request<ResourceUpdateResult>(`admin/resources/${resourceId}/`, { method: 'PATCH', body: JSON.stringify(fields) })
export const archiveResource = (resourceId: string) => post<Resource>(`admin/resources/${resourceId}/archive/`, {})
export const restoreResource = (resourceId: string) => post<Resource>(`admin/resources/${resourceId}/restore/`, {})

// Sprint 3: usage report (Manager) ---------------------------------------------------------------------------
export const getUsageReport = (firstDate: string, lastDate: string) =>
  request<UsageReport>(`admin/reports/usage/?${new URLSearchParams({ first_date: firstDate, last_date: lastDate })}`)

// Sprint 3: staff change their own password ------------------------------------------------------------------
export const changePassword = (currentPassword: string, newPassword: string) =>
  post<{ changed: boolean }>('auth/change-password/', { current_password: currentPassword, new_password: newPassword })

// Sprint 3 (1.16.0): lab setup (Manager), the lab's contact details and the staff "Today" page -----------------
export const createRequirement = (fields: Partial<RequirementInput> & { name: string }) =>
  post<Requirement>('admin/qualification-requirements/', fields)
export const updateRequirement = (requirementId: string, fields: Partial<RequirementInput> & { prerequisite_ids?: string[] }) =>
  request<Requirement>(`admin/qualification-requirements/${requirementId}/`, { method: 'PATCH', body: JSON.stringify(fields) })
export const getSiteContact = () => request<SiteContact>('site/contact/')
export const updateSiteContact = (fields: Partial<SiteContact>) =>
  request<SiteContact>('site/contact/', { method: 'PATCH', body: JSON.stringify(fields) })
export const getStaffOverview = () => request<StaffOverview>('admin/overview/')

// Sprint 3 (1.19.0): public announcements do not generate personal notifications.
export const listAnnouncements = (includeEnded = false) => request<ListResponse<Announcement>>(`announcements/${includeEnded ? '?include_ended=true' : ''}`)
export const createAnnouncement = (values: { title: string; body: string; expires_at: string | null }) => post<Announcement>('announcements/', values)
export const updateAnnouncement = (id: string, values: { title: string; body: string; expires_at: string | null }) => request<Announcement>(`announcements/${id}/`, { method: 'PATCH', body: JSON.stringify(values) })
export const removeAnnouncement = (id: string) => post<Announcement>(`announcements/${id}/remove/`, {})
