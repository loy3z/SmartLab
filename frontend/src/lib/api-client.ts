/** Shared transport for every feature. Authentication belongs to the application shell. */
export const AUTH_CHANGE_EVENT = 'smartlab:auth-change'
export const AUTH_REFRESH_EVENT = 'smartlab:auth-refresh'
export const TOKEN_KEY = 'access_token'
let memoryToken: string | null = null
let memoryOnly = false

export function getToken(): string | null {
  if (memoryOnly) return memoryToken
  try { return localStorage.getItem(TOKEN_KEY) } catch { return memoryToken }
}

export function setToken(token: string | null, reason: 'login' | 'logout' | 'expired' = token ? 'login' : 'logout') {
  memoryToken = token
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
    memoryOnly = false
  } catch { memoryOnly = true /* Restricted storage still permits a session in this tab. */ }
  window.dispatchEvent(new CustomEvent(AUTH_CHANGE_EVENT, { detail: { reason } }))
}

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

async function response(path: string, init: RequestInit, authenticated: boolean): Promise<Response> {
  const token = authenticated ? getToken() : null
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  else headers.delete('Authorization')
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  let result: Response
  try {
    result = await fetch(`/api/v1/${path}`, { ...init, headers })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(0, 'NETWORK_ERROR', 'Unable to reach SmartLab. Check your connection and try again.')
  }
  if (!result.ok) {
    const body = await result.json().catch(() => null)
    // An old request must never sign out a newer account.
    if (result.status === 401 && token && getToken() === token) setToken(null, 'expired')
    if (result.status === 403 && token && getToken() === token && path !== 'auth/me/') {
      window.dispatchEvent(new Event(AUTH_REFRESH_EVENT))
    }
    throw new ApiError(result.status, body?.error?.code ?? 'HTTP_ERROR',
      body?.error?.message ?? `Request failed (${result.status}). Please try again.`, body?.error?.details ?? {})
  }
  return result
}

export async function request<T>(path: string, init: RequestInit = {}, options: { authenticated?: boolean } = {}): Promise<T> {
  const result = await response(path, init, options.authenticated !== false)
  if (result.status === 204) return undefined as T
  try { return await result.json() as T } catch {
    throw new ApiError(result.status, 'INVALID_RESPONSE', 'The server returned an unexpected response. Please try again.')
  }
}

export async function requestBlob(path: string): Promise<Blob> {
  return (await response(path, {}, true)).blob()
}
