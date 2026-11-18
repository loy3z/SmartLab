import type { Role } from '../api/types/index.ts'

const permissions: Record<string, readonly Role[]> = {
  '/dashboard': ['STUDENT'],
  // Everyone books under the same rules; staff may also book on behalf of someone.
  '/resources': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/bookings': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/induction': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/admin/today': ['ADMIN', 'MANAGER'], // Staff home page
  '/admin/qualifications': ['ADMIN', 'MANAGER'],
  '/admin/bookings': ['ADMIN', 'MANAGER'],
  '/admin/calendar-sync': ['ADMIN', 'MANAGER'],
  '/manager/home': ['MANAGER'], // Manager home page
  '/manager/bookings': ['MANAGER'],
  '/manager/users': ['MANAGER'],
  '/manager/resources': ['MANAGER'], // Resource setup
  '/manager/setup': ['MANAGER'], // Inductions and the lab's contact details
  '/admin/records': ['ADMIN', 'MANAGER'], // Booking Records (records and usage statistics)
  '/manager/usage': ['MANAGER'], // Old Usage Report address, redirects to Booking Records (Managers only)
  '/settings/notifications': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/admin/announcements': ['ADMIN', 'MANAGER'],
  '/account': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/help': ['STUDENT', 'ADMIN', 'MANAGER'],
}

// React Router parses the hash and query string; policy checks use its pathname.
export function normalizePath(pathname: string): string {
  return pathname.replace(/\/+$/, '') || '/'
}

export function homePath(role: Role): string {
  // Staff start on "Today". A Manager starts on the Lab overview.
  return role === 'STUDENT' ? '/dashboard' : role === 'MANAGER' ? '/manager/home' : '/admin/today'
}

export function isKnownPath(path: string): boolean { return Object.hasOwn(permissions, path) }
export function canAccess(path: string, role: Role): boolean { return isKnownPath(path) && permissions[path].includes(role) }

export function loginDestination(state: unknown, role: Role): string {
  const from = state && typeof state === 'object' && 'from' in state ? state.from : null
  if (typeof from === 'string' && canAccess(normalizePath(from.split('?')[0]), role)) return from
  return homePath(role)
}
