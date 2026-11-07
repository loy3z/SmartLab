// Sprint 3 (2026-10-27): moved from the booking feature folder; function bodies unchanged.
import { request, requestBlob } from '../lib/api-client'
import { post } from './client'
import type { ListResponse } from './types/common'
import type { Availability, DayOverview, DayOverviewQuery, Qualification, Requirement, RequirementInput, Resource, ResourceInput, ResourceInternalInfo, ResourceInternalInput, ResourceKind, ResourceUpdateResult } from './types/resources'

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
  options: { forZid?: string; urgent?: boolean; additionalHours?: boolean; longBooking?: boolean } = {},
) {
  const qs = new URLSearchParams({ date, duration_minutes: String(durationMinutes) })
  if (excludeBookingId) qs.set('exclude_booking_id', excludeBookingId)
  if (options.forZid) qs.set('for_zid', options.forZid)
  if (options.urgent) qs.set('urgent', 'true')
  if (options.additionalHours) qs.set('additional_hours', 'true')
  if (options.longBooking) qs.set('long_booking', 'true')
  return request<Availability>(`resources/${id}/availability/?${qs}`)
}

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


export const downloadQualification = (id: string) => requestBlob(`qualifications/${id}/file/`)

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

// Sprint 3: resource setup (Manager) ------------------------------------------------------------------------
export const listAllResources = () => request<ListResponse<Resource>>('admin/resources/')

export const createResource = (kind: ResourceKind, fields: ResourceInput) =>
  post<Resource>('admin/resources/', { kind, ...fields })

export const updateResource = (resourceId: string, fields: Partial<ResourceInput>) =>
  request<ResourceUpdateResult>(`admin/resources/${resourceId}/`, { method: 'PATCH', body: JSON.stringify(fields) })

/** 2026-11-07 (client, Week 8), Manager only: owner, asset number, where it came from, specifications. */
export const getResourceInternalInfo = (resourceId: string) => request<ResourceInternalInfo>(`admin/resources/${resourceId}/internal/`)

export const updateResourceInternalInfo = (resourceId: string, fields: Partial<ResourceInternalInput>) =>
  request<ResourceInternalInfo>(`admin/resources/${resourceId}/internal/`, { method: 'PATCH', body: JSON.stringify(fields) })

export const archiveResource = (resourceId: string) => post<Resource>(`admin/resources/${resourceId}/archive/`, {})

export const restoreResource = (resourceId: string) => post<Resource>(`admin/resources/${resourceId}/restore/`, {})


// Sprint 3 (1.16.0): lab setup (Manager), the lab's contact details and the staff "Today" page -----------------
export const createRequirement = (fields: Partial<RequirementInput> & { name: string }) =>
  post<Requirement>('admin/qualification-requirements/', fields)

export const updateRequirement = (requirementId: string, fields: Partial<RequirementInput> & { prerequisite_ids?: string[] }) =>
  request<Requirement>(`admin/qualification-requirements/${requirementId}/`, { method: 'PATCH', body: JSON.stringify(fields) })
