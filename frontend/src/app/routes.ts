import type { Role } from '../features/booking/types.ts'

const permissions: Record<string, readonly Role[]> = {
  '/dashboard': ['STUDENT'],
  // Everyone books under the same rules; staff may also book on behalf of someone.
  '/resources': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/bookings': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/induction': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/admin/today': ['ADMIN', 'MANAGER'], // Sprint 3 (1.16.0): staff home page
  '/admin/qualifications': ['ADMIN', 'MANAGER'],
  '/admin/bookings': ['ADMIN', 'MANAGER'],
  '/admin/freezes': ['ADMIN', 'MANAGER'], // Sprint 3: booking freezes
  '/admin/calendar-sync': ['ADMIN', 'MANAGER'],
  '/manager/bookings': ['MANAGER'],
  '/manager/users': ['MANAGER'],
  '/manager/resources': ['MANAGER'], // Sprint 3: resource setup
  '/manager/setup': ['MANAGER'], // Sprint 3 (1.16.0): inductions and the lab's contact details
  '/admin/records': ['ADMIN', 'MANAGER'], // Sprint 3: Booking Records (records and usage statistics)
  '/manager/usage': ['ADMIN', 'MANAGER'], // Sprint 3: old Usage Report address, redirects to Booking Records
  '/account': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/help': ['STUDENT', 'ADMIN', 'MANAGER'],
}

// React Router parses the hash and query string; policy checks use its pathname.
export function normalizePath(pathname: string): string {
  return pathname.replace(/\/+$/, '') || '/'
}

export function homePath(role: Role): string {
  // Sprint 3 (1.16.0): Admins and Managers start on "Today" (was Qualification Review / Room Management).
  return role === 'STUDENT' ? '/dashboard' : '/admin/today'
}

export function isKnownPath(path: string): boolean { return Object.hasOwn(permissions, path) }
export function canAccess(path: string, role: Role): boolean { return isKnownPath(path) && permissions[path].includes(role) }

export function loginDestination(state: unknown, role: Role): string {
  const from = state && typeof state === 'object' && 'from' in state ? state.from : null
  if (typeof from === 'string' && canAccess(normalizePath(from.split('?')[0]), role)) return from
  return homePath(role)
}
