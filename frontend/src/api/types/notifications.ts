// Moved from the booking feature folder; definitions unchanged.

export interface AppNotification {
  id: string
  recipient_id: string
  kind: string
  title: string
  body: string
  created_at: string
  /** App page to open, e.g. "/bookings". */
  link: string | null
  booking_id: string | null
  read_at: string | null
}

export interface NotificationList {
  count: number
  unread_count: number
  results: AppNotification[]
}

/** Independent delivery choices; missing preferences default to both channels on. */
export interface NotificationPreference {
  category: string
  in_app: boolean
  email: boolean
}
