// Sprint 3 (2026-10-27): moved from the booking feature folder; function bodies unchanged.
import { request } from '../lib/api-client'
import { post } from './client'
import type { PersonBrief } from './types/resources'
import type { CalendarLink, SiteContact } from './types/site'

export const getSiteContact = () => request<SiteContact>('site/contact/')

export const updateSiteContact = (fields: Partial<SiteContact>) =>
  request<SiteContact>('site/contact/', { method: 'PATCH', body: JSON.stringify(fields) })

// Sprint 3: calendar subscription link ---------------------------------------------------------------------------------
export const getCalendarLink = () => request<CalendarLink>('calendar/link/')

export const resetCalendarLink = () => post<CalendarLink>('calendar/link/reset/', {})


/** Admin/Manager: check whom you are booking for. */
export const lookupPerson = (zid: string) =>
  request<PersonBrief>(`people/lookup/?${new URLSearchParams({ zid })}`)
