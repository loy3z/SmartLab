// Sprint 3 (2026-10-27): moved from the booking feature folder; definitions unchanged.
import type { UnfreezeRequest } from './admin'

export type Role = 'STUDENT' | 'ADMIN' | 'MANAGER'

export interface User {
  test_account?: boolean
  bypass_booking_rules?: boolean
  id: string
  zid: string
  display_name: string
  role: Role
  university_email: string
  active: boolean
  /** Sprint 3: missed check-ins since the last freeze. */
  no_show_count?: number
  frozen_until?: string | null
  /** True while booking is frozen (frozen_until is in the future). */
  booking_frozen?: boolean
}

export interface UserInduction {
  requirement_id: string
  name: string
  status:
    | 'NOT_SUBMITTED'
    | 'PENDING'
    | 'VERIFIED'
    | 'REJECTED'
    | 'EXPIRED'
  valid_until: string | null
}

export interface ManagedUser extends User {
  /** Admins and Managers are staff accounts; students are never promoted to staff. */
  is_staff: boolean
  /** Staff only: AWAITING_ACTIVATION until they choose a password with the invite code. Null for students. */
  activation_status: 'AWAITING_ACTIVATION' | 'ACTIVATED' | null
  /** Staff only, while awaiting activation: the code the Manager hands over. */
  invite_code: string | null
  inductions: UserInduction[]
  induction_status: 'VERIFIED' | 'INCOMPLETE'
}


export interface AuthResponse {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  user: User
  mode: 'demo'
}

export interface AuthConfig {
  test_console_enabled?: boolean
  mode: 'demo' | 'external_provider_required'
  demo_auth_enabled: boolean
  demo_registration_enabled: boolean
  sso_connected: boolean
  token_type: 'Bearer'
  /** Admins and Managers sign in on the staff page with zID + password. */
  staff_sign_in_enabled?: boolean
}

export interface FrozenUser extends User {
  pending_request: UnfreezeRequest | null
}
