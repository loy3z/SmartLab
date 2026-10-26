// Sprint 3 (1.16.0): helpers for the lab's contact details (set by a Manager on Lab setup).
import type { SiteContact } from '../../api/types/index.ts'

/** True when the Manager has filled in at least one contact field. */
export function hasContact(contact: SiteContact | null | undefined): boolean {
  return Boolean(contact && (contact.email || contact.phone || contact.hours || contact.note))
}

/** mailto: link with the subject and body filled in (e.g. a booking's reference and time), or '' without an email. */
export function mailtoLink(contact: SiteContact | null | undefined, subject: string, body = ''): string {
  if (!contact?.email) return ''
  const query = new URLSearchParams({ subject, ...(body ? { body } : {}) }).toString().replaceAll('+', '%20')
  return `mailto:${contact.email}?${query}`
}
