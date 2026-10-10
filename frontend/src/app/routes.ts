import type { Role } from '../features/booking/types.ts'

const permissions: Record<string, readonly Role[]> = {
  '/dashboard': ['STUDENT'],
  '/resources': ['STUDENT'],
  '/bookings': ['STUDENT'],
  '/induction': ['STUDENT'],
  '/admin/qualifications': ['ADMIN', 'MANAGER'],
  '/admin/bookings': ['ADMIN', 'MANAGER'],
  '/manager/bookings': ['MANAGER'],
  '/account': ['STUDENT', 'ADMIN', 'MANAGER'],
  '/help': ['STUDENT', 'ADMIN', 'MANAGER'],
}

export function normalizePath(hash: string): string {
  const path = hash.replace(/^#/, '').split('?')[0].replace(/\/+$/, '')
  return path || '/'
}

export function homePath(role: Role): string {
  return role === 'MANAGER' ? '/manager/bookings' : role === 'ADMIN' ? '/admin/qualifications' : '/dashboard'
}

export function isKnownPath(path: string): boolean { return Object.hasOwn(permissions, path) }
export function canAccess(path: string, role: Role): boolean { return isKnownPath(path) && permissions[path].includes(role) }
