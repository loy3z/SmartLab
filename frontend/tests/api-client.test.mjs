import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import {
  ApiError,
  AUTH_CHANGE_EVENT,
  getToken,
  request,
  requestBlob,
  setToken,
} from '../src/lib/api-client.ts'

const originalGlobals = new Map()

function installGlobal(name, value) {
  originalGlobals.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
  Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}

function unauthorizedResponse() {
  return jsonResponse({ error: { code: 'TOKEN_EXPIRED', message: 'The token has expired.', details: {} } }, 401)
}

function isApiError(status, code) {
  return (error) => {
    assert.ok(error instanceof ApiError)
    if (status !== undefined) assert.equal(error.status, status)
    assert.equal(error.code, code)
    return true
  }
}

beforeEach(() => {
  const stored = new Map()
  const storage = {
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => stored.set(key, String(value)),
    removeItem: (key) => stored.delete(key),
    clear: () => stored.clear(),
  }
  installGlobal('localStorage', storage)
  installGlobal('window', Object.assign(new EventTarget(), { localStorage: storage }))
  installGlobal('fetch', async () => { throw new Error('Test did not provide a fetch response.') })
  setToken(null)
})

afterEach(() => {
  for (const [name, descriptor] of originalGlobals) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor)
    else delete globalThis[name]
  }
  originalGlobals.clear()
})

test('JSON requests attach the current token and preserve caller headers', async () => {
  setToken('student-token')
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/v1/bookings/')
    const headers = new Headers(init.headers)
    assert.equal(headers.get('Authorization'), 'Bearer student-token')
    assert.equal(headers.get('Content-Type'), 'application/json')
    assert.equal(headers.get('Idempotency-Key'), 'booking-request-1')
    assert.equal(init.method, 'POST')
    assert.deepEqual(JSON.parse(init.body), { purpose: 'Study' })
    return jsonResponse({ id: 'created-booking' }, 201)
  }

  assert.deepEqual(await request('bookings/', {
    method: 'POST',
    headers: { 'Idempotency-Key': 'booking-request-1' },
    body: JSON.stringify({ purpose: 'Study' }),
  }), { id: 'created-booking' })
})

test('public authentication requests omit bearer credentials', async () => {
  setToken('existing-token')
  globalThis.fetch = async (_url, init) => {
    assert.equal(new Headers(init.headers).has('Authorization'), false)
    return jsonResponse({ mode: 'demo' })
  }
  await request('auth/config/', {}, { authenticated: false })
  assert.equal(getToken(), 'existing-token')
})

test('failed demo login leaves an existing session intact', async () => {
  setToken('existing-token')
  const events = []
  window.addEventListener(AUTH_CHANGE_EVENT, (event) => events.push(event.detail.reason))
  globalThis.fetch = async (_url, init) => {
    assert.equal(new Headers(init.headers).has('Authorization'), false)
    return jsonResponse({ error: { code: 'INVALID_DEMO_USER', message: 'Unknown demo user.', details: {} } }, 401)
  }

  await assert.rejects(request('auth/demo-login/', {
    method: 'POST', body: JSON.stringify({ zid: 'z1234567' }),
  }, { authenticated: false }), isApiError(401, 'INVALID_DEMO_USER'))
  assert.equal(getToken(), 'existing-token')
  assert.deepEqual(events, [])
})

test('multipart uploads let the browser supply the boundary', async () => {
  setToken('student-token')
  const form = new FormData()
  form.set('title', 'Training evidence')
  form.set('file', new Blob(['%PDF-1.4\n%%EOF'], { type: 'application/pdf' }), 'training.pdf')
  globalThis.fetch = async (_url, init) => {
    assert.equal(init.body, form)
    assert.equal(new Headers(init.headers).has('Content-Type'), false)
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer student-token')
    return jsonResponse({ status: 'PENDING' }, 201)
  }
  assert.deepEqual(await request('qualifications/', { method: 'POST', body: form }), { status: 'PENDING' })
})

test('401 for the active token clears the session and announces expiration', async () => {
  setToken('expired-token')
  const reasons = []
  window.addEventListener(AUTH_CHANGE_EVENT, (event) => reasons.push(event.detail.reason))
  globalThis.fetch = async () => unauthorizedResponse()

  await assert.rejects(request('auth/me/'), isApiError(401, 'TOKEN_EXPIRED'))
  assert.equal(getToken(), null)
  assert.deepEqual(reasons, ['expired'])
})

test('a late 401 from a previous session cannot sign out the new account', async () => {
  setToken('old-token')
  let resolveResponse
  globalThis.fetch = (_url, init) => {
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer old-token')
    return new Promise((resolve) => { resolveResponse = resolve })
  }
  const oldRequest = request('dashboard/')
  setToken('new-token', 'login')
  const reasons = []
  window.addEventListener(AUTH_CHANGE_EVENT, (event) => reasons.push(event.detail.reason))
  resolveResponse(unauthorizedResponse())

  await assert.rejects(oldRequest, isApiError(401, 'TOKEN_EXPIRED'))
  assert.equal(getToken(), 'new-token')
  assert.deepEqual(reasons, [])
})

test('network failure reports a retryable error without deleting the token', async () => {
  setToken('valid-token')
  const reasons = []
  window.addEventListener(AUTH_CHANGE_EVENT, (event) => reasons.push(event.detail.reason))
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }

  await assert.rejects(request('auth/me/'), isApiError(undefined, 'NETWORK_ERROR'))
  assert.equal(getToken(), 'valid-token')
  assert.deepEqual(reasons, [])
})

test('403 does not destroy an authenticated session', async () => {
  setToken('student-token')
  globalThis.fetch = async () => jsonResponse({
    error: { code: 'FORBIDDEN', message: 'This action requires an Admin or Manager account.', details: {} },
  }, 403)

  await assert.rejects(request('admin/bookings/'), isApiError(403, 'FORBIDDEN'))
  assert.equal(getToken(), 'student-token')
})

test('a malformed successful JSON response is reported rather than accepted as data', async () => {
  setToken('valid-token')
  globalThis.fetch = async () => new Response('<html>Proxy error</html>', { status: 200 })

  await assert.rejects(request('dashboard/'), isApiError(undefined, 'INVALID_RESPONSE'))
  assert.equal(getToken(), 'valid-token')
})

test('a legitimate empty 204 response does not require JSON', async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 })
  await assert.doesNotReject(request('bookings/example/', { method: 'DELETE' }))
})

test('protected evidence downloads carry the token and return the file', async () => {
  setToken('admin-token')
  globalThis.fetch = async (_url, init) => {
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer admin-token')
    return new Response('%PDF-1.4\n%%EOF', { headers: { 'Content-Type': 'application/pdf' } })
  }

  const file = await requestBlob('qualifications/example/file/')
  assert.ok(file instanceof Blob)
  assert.equal(file.type, 'application/pdf')
  assert.equal(await file.text(), '%PDF-1.4\n%%EOF')
})

test('expired evidence-download sessions follow the same 401 handling as JSON requests', async () => {
  setToken('expired-admin-token')
  const reasons = []
  window.addEventListener(AUTH_CHANGE_EVENT, (event) => reasons.push(event.detail.reason))
  globalThis.fetch = async () => unauthorizedResponse()

  await assert.rejects(requestBlob('qualifications/example/file/'), isApiError(401, 'TOKEN_EXPIRED'))
  assert.equal(getToken(), null)
  assert.deepEqual(reasons, ['expired'])
})

test('readable storage with failed writes uses the new token in memory and can sign out', async () => {
  setToken('previously-stored-token')
  localStorage.setItem = () => { throw new DOMException('Storage quota exceeded.', 'QuotaExceededError') }
  setToken('new-tab-token', 'login')

  assert.equal(getToken(), 'new-tab-token')
  globalThis.fetch = async (_url, init) => {
    assert.equal(new Headers(init.headers).get('Authorization'), 'Bearer new-tab-token')
    return jsonResponse({ id: 'new-user' })
  }
  assert.deepEqual(await request('auth/me/'), { id: 'new-user' })

  setToken(null, 'logout')
  assert.equal(getToken(), null)
})

test('failed storage removal still expires the in-memory session without reusing the stale token', async () => {
  setToken('expired-stored-token')
  localStorage.removeItem = () => { throw new DOMException('Storage writes blocked.', 'SecurityError') }
  const reasons = []
  window.addEventListener(AUTH_CHANGE_EVENT, (event) => reasons.push(event.detail.reason))
  globalThis.fetch = async () => unauthorizedResponse()

  await assert.rejects(request('auth/me/'), isApiError(401, 'TOKEN_EXPIRED'))
  assert.equal(getToken(), null)
  assert.deepEqual(reasons, ['expired'])

  globalThis.fetch = async (_url, init) => {
    assert.equal(new Headers(init.headers).has('Authorization'), false)
    return unauthorizedResponse()
  }
  await assert.rejects(request('auth/me/'), isApiError(401, 'TOKEN_EXPIRED'))
  assert.deepEqual(reasons, ['expired'])
})
