// Moved from the booking feature folder; definitions unchanged.

export interface CalendarLink {
  /** Relative path of the subscription feed; prefix with the site address. */
  path: string
  created_at: string
}

/** The lab's contact details (GET/PATCH site/contact/); empty fields are not shown. */
export interface SiteContact {
  email: string
  phone: string
  hours: string
  note: string
  updated_at?: string | null
}

