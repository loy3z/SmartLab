// Sprint 3 (2026-10-27): moved from the booking feature folder; function bodies unchanged.
import { request, requestBlob } from '../lib/api-client'
import { post } from './client'
import type { StaffOverview, UnfreezeRequest } from './types/admin'
import type { FrozenUser, ManagedUser, User } from './types/auth'
import type { Booking, CalendarCheck, CalendarSyncStatus } from './types/bookings'
import type { ListResponse } from './types/common'
import type { Qualification, Resource, ResourceStatus, UsageReport } from './types/resources'

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


export const listFrozenUsers = () => request<ListResponse<FrozenUser>>('admin/frozen-users/')

export function listUnfreezeRequests(status?: 'PENDING' | 'APPROVED' | 'REJECTED') {
  const qs = new URLSearchParams()
  if (status) qs.set('status', status)
  return request<ListResponse<UnfreezeRequest>>(`admin/unfreeze-requests/?${qs}`)
}

export const reviewUnfreeze = (id: string, decision: 'APPROVED' | 'REJECTED', reason = '') =>
  post<UnfreezeRequest>(`admin/unfreeze-requests/${id}/review/`, { decision, reason })

export const unfreezeUser = (userId: string, reason = '') => post<User>(`admin/users/${userId}/unfreeze/`, { reason })


// Sprint 3: usage report (Manager) ---------------------------------------------------------------------------
export const getUsageReport = (firstDate: string, lastDate: string) =>
  request<UsageReport>(`admin/reports/usage/?${new URLSearchParams({ first_date: firstDate, last_date: lastDate })}`)


export const getStaffOverview = () => request<StaffOverview>('admin/overview/')


// Calendar Sync (Admin and Manager). Reading the status never calls Microsoft; the actions do.
export const getCalendarSync = () => request<CalendarSyncStatus>('admin/outlook/')

export const checkCalendarConnection = () => post<CalendarCheck>('admin/outlook/check/', {})

export const processCalendarSync = () => post<{ processed_count: number }>('admin/outlook/process/', { limit: 5 })

export const retryCalendarSync = (bookingId: string) => post<Booking>(`admin/bookings/${bookingId}/outlook-retry/`, {})


export const listMyUnfreezeRequests = () => request<ListResponse<UnfreezeRequest>>('account/unfreeze-requests/')

export const requestUnfreeze = (reason: string) => post<UnfreezeRequest>('account/unfreeze-requests/', { reason })
