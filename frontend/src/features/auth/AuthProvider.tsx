import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { getMe } from '../booking/api'
import { errorMessage } from '../booking/format'
import { AUTH_CHANGE_EVENT, AUTH_REFRESH_EVENT, getToken, setToken, TOKEN_KEY } from '../../lib/api-client'
import { AuthContext, type AuthState } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => ({ status: getToken() ? 'loading' : 'anonymous', user: null, error: '', notice: '' }))
  const generation = useRef(0)
  const mounted = useRef(false)
  const authenticated = useRef(false)

  const verify = useCallback((token: string, background = false) => {
    const run = ++generation.current
    return getMe().then((user) => {
      if (mounted.current && run === generation.current && getToken() === token) {
        authenticated.current = true
        setState({ status: 'authenticated', user, error: '', notice: '' })
      }
    }).catch((error: unknown) => {
      if (!mounted.current || run !== generation.current || getToken() !== token) return
      // Network failures retain the token so Retry can restore the same session.
      if (!background) setState({ status: 'error', user: null, error: errorMessage(error), notice: '' })
    })
  }, [])

  const restore = useCallback((background = false, notice = '') => {
    const token = getToken()
    if (!background) authenticated.current = false
    if (!token) {
      generation.current++
      setState({ status: 'anonymous', user: null, error: '', notice })
      return
    }
    if (!background) setState({ status: 'loading', user: null, error: '', notice })
    void verify(token, background)
  }, [verify])

  useEffect(() => {
    mounted.current = true
    const change = (event: Event) => {
      const expired = (event as CustomEvent<{ reason: string }>).detail?.reason === 'expired'
      void restore(false, expired ? 'Your session has expired. Please sign in again.' : '')
    }
    const storage = (event: StorageEvent) => { if (event.key === TOKEN_KEY || event.key === null) void restore() }
    // Do not let a background request supersede an in-flight foreground restore.
    const refresh = () => { if (authenticated.current && getToken()) restore(true) }
    window.addEventListener(AUTH_CHANGE_EVENT, change)
    window.addEventListener(AUTH_REFRESH_EVENT, refresh)
    window.addEventListener('storage', storage)
    window.addEventListener('focus', refresh)
    const token = getToken()
    if (token) void verify(token)
    return () => {
      mounted.current = false
      window.removeEventListener(AUTH_CHANGE_EVENT, change)
      window.removeEventListener(AUTH_REFRESH_EVENT, refresh)
      window.removeEventListener('storage', storage)
      window.removeEventListener('focus', refresh)
    }
  }, [restore, verify])

  return <AuthContext.Provider value={{ ...state, retry: () => { void restore() }, signOut: () => setToken(null) }}>{children}</AuthContext.Provider>
}
