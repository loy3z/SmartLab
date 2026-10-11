import { expect, test as base, type Page } from '@playwright/test'
import type { AuthConfig, Dashboard, Role, User } from '../src/features/booking/types'

// Synthetic accounts exist only in these intercepted responses. No real backend is used.
const users: Record<Role, User> = {
  STUDENT: { id: 'test-student', zid: 'z1000001', display_name: 'Test Student', role: 'STUDENT', university_email: 'student@example.test', active: true },
  ADMIN: { id: 'test-admin', zid: 'z9000001', display_name: 'Test Admin', role: 'ADMIN', university_email: 'admin@example.test', active: true },
  MANAGER: { id: 'test-manager', zid: 'z9000002', display_name: 'Test Manager', role: 'MANAGER', university_email: 'manager@example.test', active: true },
}
const unqualifiedStudent: User = { ...users.STUDENT, id: 'test-unqualified-student', zid: 'z1000002', display_name: 'Test Unqualified Student' }
const accounts = [...Object.values(users), unqualifiedStudent]
const config: AuthConfig = { mode: 'demo', demo_auth_enabled: true, demo_registration_enabled: false, sso_connected: false, token_type: 'Bearer' }
const dashboard: Dashboard = {
  bookings: [], qualifications: [],
  counts: { WAITING_QUALIFICATION: 0, WAITLISTED: 0, PENDING_APPROVAL: 0, APPROVED: 0, REJECTED: 0, CANCELLED: 0, EXPIRED: 0 },
}
const emptyList = { count: 0, results: [] }
interface MockApi {
  me: 'ok' | 'offline' | 'expired'
  config: AuthConfig
  login: 'ok' | 'offline' | 'rejected'
  loginGate: Promise<void> | null
  verifiedRole: Role | null
  loginBodies: unknown[]
  unexpected: string[]
  requests: string[]
}

const test = base.extend<{ api: MockApi }>({
  api: [async ({ page }, use) => {
    const api: MockApi = { me: 'ok', config: { ...config }, login: 'ok', loginGate: null, verifiedRole: null, loginBodies: [], unexpected: [], requests: [] }
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname.replace('/api/v1/', '')
      api.requests.push(path)
      const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
      if (path === 'auth/config/') return json(api.config)
      if (path === 'auth/demo-login/' && request.method() === 'POST') {
        api.loginBodies.push(request.postDataJSON())
        if (api.loginGate) await api.loginGate
        if (api.login === 'offline') return route.abort('internetdisconnected')
        if (api.login === 'rejected') return json({ error: { code: 'DEMO_LOGIN_REJECTED', message: 'The selected demo account is unavailable.' } }, 403)
        const user = accounts.find((item) => item.zid === request.postDataJSON().zid)
        if (user) {
          // A stale login role must never override the identity returned by auth/me.
          const identity = api.verifiedRole ? users[api.verifiedRole] : user
          return json({ access_token: `test-token-${identity.zid}`, token_type: 'Bearer', expires_in: 3600, mode: 'demo', user })
        }
        return json({ error: { code: 'DEMO_USER_NOT_FOUND', message: 'No demo account has this zID.' } }, 404)
      }
      const user = accounts.find((item) => request.headers().authorization === `Bearer test-token-${item.zid}`)
      if (!user) {
        api.unexpected.push(`Missing test credentials: ${path}`)
        return json({ error: { code: 'UNAUTHENTICATED', message: 'Expected a synthetic test account.' } }, 401)
      }
      if (path === 'auth/me/') {
        if (api.me === 'offline') return route.abort('internetdisconnected')
        if (api.me === 'expired') return json({ error: { code: 'TOKEN_EXPIRED', message: 'Test session expired.' } }, 401)
        return json(user)
      }
      if (path === 'dashboard/') return json(dashboard)
      if (['resources/', 'bookings/', 'qualifications/', 'qualification-requirements/', 'admin/qualifications/', 'admin/bookings/'].includes(path) && request.method() === 'GET') {
        return json(emptyList)
      }
      // Fail closed: unhandled requests must never reach a real service.
      api.unexpected.push(`${request.method()} ${path}`)
      return json({ error: { code: 'UNMOCKED', message: 'Unexpected test request.' } }, 500)
    })
    await use(api)
    expect(api.unexpected, 'Every API call should be handled by synthetic test data').toEqual([])
  }, { auto: true }],
})

async function signIn(page: Page, role: Role = 'STUDENT') {
  await page.getByRole('link', { name: 'University sign-in (Demo)', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  await page.getByLabel('Demo zID or university email', { exact: true }).fill(users[role].zid)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('button', { name: `Account options for ${users[role].display_name}` })).toBeVisible()
}

async function signOut(page: Page) {
  await page.getByRole('button', { name: /^Account options for / }).click()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL(/#\/login$/)
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
}

for (const { entry, destination, heading, menu } of [
  { entry: '/bookings/?view=upcoming', destination: '/bookings?view=upcoming', heading: 'My bookings', menu: 'My Bookings' },
  { entry: '/resources/?kind=ROOM', destination: '/resources?kind=ROOM', heading: 'Book a resource', menu: 'Book a Resource' },
]) {
  test(`anonymous deep link returns to ${destination} after login`, async ({ page }) => {
    await page.goto(`/#${entry}`)
    await expect(page).toHaveURL(/#\/login$/)
    await signIn(page)
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${destination}`)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: menu, exact: true })).toHaveAttribute('aria-current', 'page')
  })
}

const portals: { role: Role; home: string; heading: string; forbidden: string }[] = [
  { role: 'STUDENT', home: '/dashboard', heading: 'Welcome back, Test.', forbidden: '/admin/qualifications' },
  { role: 'ADMIN', home: '/admin/qualifications', heading: 'Induction qualification review', forbidden: '/manager/bookings' },
  { role: 'MANAGER', home: '/manager/bookings', heading: 'Room booking management', forbidden: '/resources' },
]
for (const { role, home, heading, forbidden } of portals) {
  test(`${role} gets its home, shared account page and a restricted page for a forbidden route`, async ({ page, api }) => {
    await page.goto('/#/login')
    await signIn(page, role)
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${home}`)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await page.getByRole('button', { name: /^Account options for / }).click()
    await page.getByRole('link', { name: 'Account details', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Account details', exact: true })).toBeVisible()
    await expect(page.getByText(users[role].university_email, { exact: true })).toBeVisible()
    api.requests.length = 0
    await page.goto(`/#${forbidden}`)
    await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
    expect(api.requests.filter((path) => path !== 'auth/me/')).toEqual([])
    await page.getByRole('link', { name: 'Return to my portal' }).click()
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${home}`)
  })

  test(`${role} does not return to a forbidden anonymous deep link`, async ({ page }) => {
    await page.goto(`/#${forbidden}`)
    await signIn(page, role)
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${home}`)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  })
}

test('explicit logout forgets the previous page before a new login', async ({ page }) => {
  await page.goto('/#/bookings')
  await signIn(page)
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
  await signOut(page)
  await signIn(page)
  await expect(page).toHaveURL(/#\/dashboard$/)
})

test('refresh restores a signed-in deep link including its query', async ({ page }) => {
  await page.goto('/#/bookings/?view=upcoming')
  await signIn(page)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/#\/bookings\?view=upcoming$/)
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toHaveCount(0)
})

test('an expired session requests login and returns to the allowed page', async ({ page, api }) => {
  await page.goto('/#/bookings')
  await signIn(page)
  api.me = 'expired'
  await page.reload()
  await expect(page).toHaveURL(/#\/login$/)
  await expect(page.getByText('Your session has expired. Please sign in again.', { exact: true })).toBeVisible()
  api.me = 'ok'
  await signIn(page)
  await expect(page).toHaveURL(/#\/bookings$/)
})

test('network failure on refresh keeps the session so Retry restores the same page', async ({ page, api }) => {
  await page.goto('/#/account')
  await signIn(page)
  api.me = 'offline'
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Unable to restore your session' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('Unable to reach SmartLab')
  api.me = 'ok'
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Account details', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/#\/account$/)
})

test('Back to sign in after a restore failure starts a fresh login', async ({ page, api }) => {
  await page.goto('/#/bookings')
  await signIn(page)
  api.me = 'offline'
  await page.reload()
  await page.getByRole('button', { name: 'Back to sign in' }).click()
  api.me = 'ok'
  await signIn(page)
  await expect(page).toHaveURL(/#\/dashboard$/)
})

test('unknown and differently cased paths show a recoverable not-found page', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page)
  for (const path of ['/missing-page', '/Resources', '/__proto__']) {
    await page.goto(`/#${path}`)
    await expect(page.getByText('PAGE NOT FOUND', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Book a resource', exact: true })).toHaveCount(0)
    await page.getByRole('link', { name: 'Return to my portal' }).click()
    await expect(page).toHaveURL(/#\/dashboard$/)
  }
})

test('menu navigation and browser history keep the active link in sync', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page)
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true })
  const resources = navigation.getByRole('link', { name: 'Book a Resource', exact: true })
  const bookings = navigation.getByRole('link', { name: 'My Bookings', exact: true })
  await resources.click()
  await expect(resources).toHaveAttribute('aria-current', 'page')
  await bookings.click()
  await expect(bookings).toHaveAttribute('aria-current', 'page')
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Book a resource', exact: true })).toBeVisible()
  await expect(resources).toHaveAttribute('aria-current', 'page')
  await page.goForward()
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
  await expect(bookings).toHaveAttribute('aria-current', 'page')
})

test('mobile menu navigates and closes, and Escape dismisses it', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/login')
  await signIn(page)
  const toggle = page.getByRole('button', { name: 'Open navigation' })
  const dialog = page.getByRole('dialog', { name: 'Navigation', exact: true })
  await toggle.click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('link', { name: 'My Bookings', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
  await expect(dialog).not.toBeVisible()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
})

for (const { label, user, home } of [
  { label: 'Student with induction', user: users.STUDENT, home: '/dashboard' },
  { label: 'Student without induction', user: unqualifiedStudent, home: '/dashboard' },
  { label: 'Administrator', user: users.ADMIN, home: '/admin/qualifications' },
  { label: 'Manager', user: users.MANAGER, home: '/manager/bookings' },
]) {
  test(`mock university sign-in authenticates ${label} through the API`, async ({ page, api }) => {
    await page.goto('/#/login')
    await page.getByRole('link', { name: 'University sign-in (Demo)', exact: true }).click()
    await expect(page).toHaveURL(/#\/login\/mock-sso$/)
    await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
    await expect(page.getByText('Mock SSO', { exact: true })).toBeVisible()
    await expect(page.getByText(/University SSO is not connected/)).toBeVisible()
    await expect(page.locator('input[type="password"]')).toHaveCount(0)
    await page.getByLabel('Demo zID or university email', { exact: true }).fill(user.zid)
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(page.getByRole('button', { name: `Account options for ${user.display_name}` })).toBeVisible()
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${home}`)
    expect(api.loginBodies).toEqual([{ zid: user.zid }])
    expect(api.requests).toContain('auth/me/')
  })
}

test('mock sign-in preserves an intended destination across cancellation, history and refresh', async ({ page, api }) => {
  await page.goto('/#/bookings/?view=upcoming')
  const openUniversitySignIn = () => page.getByRole('link', { name: 'University sign-in (Demo)', exact: true }).click()
  await openUniversitySignIn()
  await expect(page.getByLabel('Demo zID or university email', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Back to SmartLab', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  expect(api.loginBodies).toEqual([])

  await openUniversitySignIn()
  await page.goBack()
  await expect(page).toHaveURL(/#\/login$/)
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  await page.goForward()
  await expect(page.getByLabel('Demo zID or university email', { exact: true })).toBeVisible()
  await page.reload()
  await page.getByLabel('Demo zID or university email', { exact: true }).fill(users.STUDENT.zid)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page).toHaveURL(/#\/bookings\?view=upcoming$/)
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
})

test('disabled demo authentication cannot be bypassed by opening the mock sign-in URL', async ({ page, api }) => {
  api.config.demo_auth_enabled = false
  for (const path of ['/login', '/login/mock-sso']) {
    await page.goto(`/#${path}`)
    await expect(page.getByRole('heading', { name: 'University sign-in is not available yet', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'University sign-in (Demo)', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Next', exact: true })).toHaveCount(0)
    await expect(page.getByLabel('Demo zID or university email', { exact: true })).toHaveCount(0)
    await expect(page.getByLabel('University zID', { exact: true })).toHaveCount(0)
  }
  expect(api.loginBodies).toEqual([])
})

for (const failure of ['offline', 'rejected'] as const) {
  test(`mock sign-in stays anonymous after ${failure} and allows a retry`, async ({ page, api }) => {
    api.login = failure
    await page.goto('/#/login/mock-sso')
    await page.getByLabel('Demo zID or university email', { exact: true }).fill(users.STUDENT.zid)
    const submit = page.getByRole('button', { name: 'Next', exact: true })
    await submit.click()
    await expect(page.getByRole('alert')).toContainText(failure === 'offline' ? 'Unable to reach SmartLab' : 'The selected demo account is unavailable.')
    await expect(page).toHaveURL(/#\/login\/mock-sso$/)
    await expect(page.getByRole('button', { name: /^Account options for / })).toHaveCount(0)
    await expect(submit).toBeEnabled()
    expect(api.requests).not.toContain('auth/me/')
    api.login = 'ok'
    await submit.click()
    await expect(page).toHaveURL(/#\/dashboard$/)
    await expect(page.getByRole('button', { name: 'Account options for Test Student' })).toBeVisible()
    expect(api.loginBodies).toEqual([{ zid: users.STUDENT.zid }, { zid: users.STUDENT.zid }])
  })
}

test('an administrator zID and login response cannot grant a role rejected by auth/me', async ({ page, api }) => {
  api.verifiedRole = 'STUDENT'
  await page.goto('/#/admin/qualifications')
  await page.getByRole('link', { name: 'University sign-in (Demo)', exact: true }).click()
  await page.getByLabel('Demo zID or university email', { exact: true }).fill(users.ADMIN.zid)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page).toHaveURL(/#\/dashboard$/)
  await expect(page.getByRole('button', { name: 'Account options for Test Student' })).toBeVisible()
  expect(api.loginBodies).toEqual([{ zid: users.ADMIN.zid }])
  expect(api.requests).toContain('auth/me/')
  expect(api.requests).not.toContain('admin/qualifications/')
  await page.goto('/#/admin/qualifications')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
})

test('the existing direct demo sign-in remains available under other options', async ({ page }) => {
  await page.goto('/#/login')
  await page.getByText('Other demo sign-in options', { exact: true }).click()
  await page.getByLabel('University zID', { exact: true }).fill(users.STUDENT.zid)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/#\/dashboard$/)
  await expect(page.getByRole('button', { name: 'Account options for Test Student' })).toBeVisible()
})

for (const identifier of ['z1000001@ad.unsw.edu.au', '  Z1000001@AD.UNSW.EDU.AU  ', '  Z1000001  ']) {
  test(`mock sign-in normalizes ${JSON.stringify(identifier)} and submits with Enter`, async ({ page, api }) => {
    await page.goto('/#/login/mock-sso')
    const input = page.getByLabel('Demo zID or university email', { exact: true })
    await input.fill(identifier)
    await input.press('Enter')
    await expect(page).toHaveURL(/#\/dashboard$/)
    await expect(page.getByRole('button', { name: 'Account options for Test Student' })).toBeVisible()
    expect(api.loginBodies).toEqual([{ zid: users.STUDENT.zid }])
  })
}

for (const identifier of ['z100000', 'student', 'z1000001@unsw.edu.au', 'z1000001@ad.unsw.edu.au.example.test']) {
  test(`mock sign-in rejects ${JSON.stringify(identifier)} before calling the API`, async ({ page, api }) => {
    await page.goto('/#/login/mock-sso')
    await page.getByLabel('Demo zID or university email', { exact: true }).fill(identifier)
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('demo zID')
    await expect(page).toHaveURL(/#\/login\/mock-sso$/)
    expect(api.loginBodies).toEqual([])
    expect(api.requests).not.toContain('auth/me/')
  })
}

test('leaving mock sign-in while a request is pending prevents a late response from logging in', async ({ page, api }) => {
  let releaseLogin!: () => void
  api.loginGate = new Promise<void>((resolve) => { releaseLogin = resolve })
  await page.goto('/#/login/mock-sso')
  await page.getByLabel('Demo zID or university email', { exact: true }).fill(users.STUDENT.zid)
  const response = page.waitForResponse('**/api/v1/auth/demo-login/')
  try {
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await expect.poll(() => api.loginBodies).toEqual([{ zid: users.STUDENT.zid }])
    await expect(page.getByRole('button', { name: 'Signing in…', exact: true })).toBeDisabled()
    await page.getByRole('link', { name: 'Back to SmartLab', exact: true }).click()
    await expect(page).toHaveURL(/#\/login$/)
  } finally {
    releaseLogin()
  }
  await (await response).finished()
  // Let the deliberately delayed response settle before checking that no session was created.
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('link', { name: 'University sign-in (Demo)', exact: true })).toBeVisible()
  expect(api.requests).not.toContain('auth/me/')
  await page.reload()
  await expect(page).toHaveURL(/#\/login$/)
  await expect(page.getByRole('link', { name: 'University sign-in (Demo)', exact: true })).toBeVisible()
  expect(api.requests).not.toContain('auth/me/')
})
