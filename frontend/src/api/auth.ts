// Sprint 3 (2026-10-27): moved from the booking feature folder; function bodies unchanged.
import { request } from '../lib/api-client'
import { post } from './client'
import type { AuthConfig, AuthResponse, User } from './types/auth'

export const getAuthConfig = () => request<AuthConfig>('auth/config/', {}, { authenticated: false })

export const testLogin = (loginId: string) => request<AuthResponse>('auth/test-login/', {
  method: 'POST', body: JSON.stringify({ login_id: loginId }),
}, { authenticated: false })

export const changeTestSession = (role: User['role'], bypass: boolean) => request<AuthResponse>('auth/test-session/', {
  method: 'POST', body: JSON.stringify({ role, bypass_booking_rules: bypass }),
})

export const demoLogin = (zid: string) => request<AuthResponse>('auth/demo-login/', {
  method: 'POST', body: JSON.stringify({ zid }),
}, { authenticated: false })

export const demoRegister = (data: { zid: string; display_name: string; university_email: string }) =>
  request<AuthResponse>('auth/demo-register/', { method: 'POST', body: JSON.stringify(data) }, { authenticated: false })
/** Staff sign-in page (Admins and Managers). Students use university sign-in. */
export const staffSignIn = (zid: string, password: string) =>
  request<AuthResponse>('auth/staff-sign-in/', { method: 'POST', body: JSON.stringify({ zid, password }) }, { authenticated: false })
/** First staff sign-in: the invite code from a Manager plus a new password. */
export const staffActivate = (data: { zid: string; invite_code: string; password: string }) =>
  request<AuthResponse>('auth/staff-activate/', { method: 'POST', body: JSON.stringify(data) }, { authenticated: false })

export const getMe = () => request<User>('auth/me/')

// Sprint 3: staff change their own password ------------------------------------------------------------------
export const changePassword = (currentPassword: string, newPassword: string) =>
  post<{ changed: boolean }>('auth/change-password/', { current_password: currentPassword, new_password: newPassword })

