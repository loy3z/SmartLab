// Sprint 3 (2026-10-27): moved from the booking feature folder; function bodies unchanged.
import { request } from '../lib/api-client'
import { post } from './client'
import type { AppNotification, NotificationList, NotificationPreference } from './types/notifications'

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

