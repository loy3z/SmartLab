import { createContext, useContext } from 'react'
import type { User } from '../booking/types'

export interface AuthState {
  status: 'loading' | 'authenticated' | 'anonymous' | 'error'
  user: User | null
  error: string
  notice: string
}
export interface AuthContextValue extends AuthState {
  retry: () => void
  signOut: () => void
}
export const AuthContext = createContext<AuthContextValue | null>(null)
export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth requires AuthProvider')
  return value
}
