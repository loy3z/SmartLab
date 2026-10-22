import type { Role } from '../features/booking/types.ts'

const permissions: Record<string, readonly Role[]> = {
  '/dashboard': ['STUDENT'],
  // Everyone books under the same rules (client, 17 Oct); staff may also book on behalf of someone.
  '/resources': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/bookings': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/induction': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/admin/qualifications': ['ADMIN', 'MANAGER'],
  '/admin/bookings': ['ADMIN', 'MANAGER'],
  '/admin/calendar-sync': ['ADMIN', 'MANAGER'],
  '/manager/bookings': ['MANAGER'],
  '/manager/users': ['MANAGER'],
  '/account': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/help': ['STUDENT', 'ADMIN', 'MANAGER'],
}

// React Router parses the hash and query string; policy checks use its pathname.
export function normalizePath(pathname: string): string {
  return pathname.replace(/\/+$/, '') || '/'
}

export function homePath(role: Role): string {
  return role === 'MANAGER' ? '/manager/bookings' : role === 'ADMIN' ? '/admin/qualifications' : '/dashboard'
}

export function isKnownPath(path: string): boolean { return Object.hasOwn(permissions, path) }
export function canAccess(path: string, role: Role): boolean { return isKnownPath(path) && permissions[path].includes(role) }

export function loginDestination(state: unknown, role: Role): string {
  const from = state && typeof state === 'object' && 'from' in state ? state.from : null
  if (typeof from === 'string' && canAccess(normalizePath(from.split('?')[0]), role)) return from
  return homePath(role)
}
