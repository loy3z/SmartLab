// Moved from the booking feature folder; function bodies unchanged.
import { request } from '../lib/api-client'
import { post } from './client'
import type { Announcement } from './types/announcements'
import type { ListResponse } from './types/common'

// Public announcements do not generate personal notifications.
export const listAnnouncements = (includeEnded = false) => request<ListResponse<Announcement>>(`announcements/${includeEnded ? '?include_ended=true' : ''}`)

export const createAnnouncement = (values: { title: string; body: string; expires_at: string | null }) => post<Announcement>('announcements/', values)

export const updateAnnouncement = (id: string, values: { title: string; body: string; expires_at: string | null }) => request<Announcement>(`announcements/${id}/`, { method: 'PATCH', body: JSON.stringify(values) })

export const removeAnnouncement = (id: string) => post<Announcement>(`announcements/${id}/remove/`, {})

// The author clears an ended announcement from the history for good.
export const deleteAnnouncement = (id: string) => request<void>(`announcements/${id}/`, { method: 'DELETE' })
