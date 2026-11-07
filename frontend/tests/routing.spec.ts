import { expect, test as base, type Page } from '@playwright/test'
import type { AuthConfig, Dashboard, Role, User } from '../src/api/types/index.ts'

// Synthetic accounts exist only in these intercepted responses. No real backend is used.
const users: Record<Role, User> = {
  STUDENT: { id: 'test-student', zid: 'z1000001', display_name: 'Test Student', role: 'STUDENT', university_email: 'student@example.test', active: true },
  ADMIN: { id: 'test-admin', zid: 'z9000001', display_name: 'Test Admin', role: 'ADMIN', university_email: 'admin@example.test', active: true },
  MANAGER: { id: 'test-manager', zid: 'z9000002', display_name: 'Test Manager', role: 'MANAGER', university_email: 'manager@example.test', active: true },
}
const unqualifiedStudent: User = { ...users.STUDENT, id: 'test-unqualified-student', zid: 'z1000002', display_name: 'Test Unqualified Student' }
const accounts = [...Object.values(users), unqualifiedStudent]
const config: AuthConfig = { mode: 'demo', demo_auth_enabled: true, demo_registration_enabled: false, sso_connected: false, token_type: 'Bearer', staff_sign_in_enabled: true }
const STAFF_PASSWORD = '123'
const dashboard: Dashboard = {
  bookings: [], qualifications: [],
  counts: { WAITING_QUALIFICATION: 0, WAITLISTED: 0, PENDING_APPROVAL: 0, APPROVED: 0, REJECTED: 0, CANCELLED: 0, EXPIRED: 0 },
  week_hours: { week_start: '2030-01-07', used_hours: 7.5, limit_hours: 12 },
}
const emptyList = { count: 0, results: [] }

// Sprint 3 (1.19.0): new notification/announcement acceptance cases use the same isolated API fixture.
interface MockApi {
  me: 'ok' | 'offline' | 'expired'
  config: AuthConfig
  login: 'ok' | 'offline' | 'rejected'
  loginGate: Promise<void> | null
  verifiedRole: Role | null
  loginBodies: unknown[]
  unexpected: string[]
  requests: string[]
  managerUserRequests: string[]
}

const test = base.extend<{ api: MockApi }>({
  api: [async ({ page }, use) => {
    const api: MockApi = { me: 'ok', config: { ...config }, login: 'ok', loginGate: null, verifiedRole: null, loginBodies: [], unexpected: [], requests: [], managerUserRequests: [] }
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname.replace('/api/v1/', '')
      api.requests.push(path)
      if (path.startsWith('admin/users/')) api.managerUserRequests.push(`${request.method()} ${path}`)
      const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
      if (path === 'auth/config/') return json(api.config)
      if (path === 'auth/demo-login/' && request.method() === 'POST') {
        api.loginBodies.push(request.postDataJSON())
        if (api.loginGate) await api.loginGate
        if (api.login === 'offline') return route.abort('internetdisconnected')
        if (api.login === 'rejected') return json({ error: { code: 'DEMO_LOGIN_REJECTED', message: 'The selected demo account is unavailable.' } }, 403)
        const user = accounts.find((item) => item.zid === request.postDataJSON().zid)
        if (user && user.role !== 'STUDENT' && !api.verifiedRole) {
          // University sign-in is for students; staff use the staff sign-in page.
          return json({ error: { code: 'USE_STAFF_SIGN_IN', message: 'Admins and Managers sign in on the staff sign-in page.' } }, 403)
        }
        if (user) {
          // A stale login role must never override the identity returned by auth/me.
          const identity = api.verifiedRole ? users[api.verifiedRole] : user
          return json({ access_token: `test-token-${identity.zid}`, token_type: 'Bearer', expires_in: 3600, mode: 'demo', user })
        }
        return json({ error: { code: 'DEMO_USER_NOT_FOUND', message: 'No demo account has this zID.' } }, 404)
      }
      if (path === 'auth/staff-sign-in/' && request.method() === 'POST') {
        const body = request.postDataJSON()
        api.loginBodies.push(body)
        const user = accounts.find((item) => item.zid === body.zid)
        if (user?.role === 'STUDENT') return json({ error: { code: 'STUDENT_USES_SSO', message: 'Students sign in with university sign-in.' } }, 403)
        if (!user || body.password !== STAFF_PASSWORD) return json({ error: { code: 'INVALID_CREDENTIALS', message: 'The zID or password is not correct.' } }, 401)
        const identity = api.verifiedRole ? users[api.verifiedRole] : user
        return json({ access_token: `test-token-${identity.zid}`, token_type: 'Bearer', expires_in: 3600, mode: 'demo', user })
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
      if (path === 'notifications/' && request.method() === 'GET') return json({ count: 0, unread_count: 0, results: [] })
      if (path === 'announcements/' && request.method() === 'GET') return json(emptyList)
      // Sprint 3 (2026-10-25): the Account page's notification switches (all on by default).
      if (path === 'notifications/preferences/' && request.method() === 'GET') {
        return json({ results: ['bookings', 'reminders', 'induction', 'account', 'resources'].map((category) => ({ category, enabled: true })) })
      }
      // Sprint 3 (1.16.0): the lab's contact details (empty until a Manager saves them) and the staff Today page.
      if (path === 'site/contact/' && request.method() === 'GET') return json({ id: 'contact', email: '', phone: '', hours: '', note: '' })
      if (path === 'admin/overview/' && request.method() === 'GET' && user.role !== 'STUDENT') return json(emptyOverview(user.role))
      // 2026-11-07: the Manager home page shows this week's usage figures.
      if (path === 'admin/reports/usage/' && request.method() === 'GET' && user.role === 'MANAGER') return json(emptyUsage)
      if (path === 'admin/users/' && request.method() === 'GET' && user.role === 'MANAGER') {
        return json({ count: accounts.length, results: accounts })
      }
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

const emptyUsage = { first_date: '2030-01-07', last_date: '2030-01-13', days: 7, results: [],
  totals: { approved: 0, booked_hours: 0, open_hours: 0, utilisation: null, checked_in: 0, no_show: 0, excused: 0, not_tracked: 0,
    attendance_rate: null, cancelled: 0, rejected: 0 } }

// Sprint 3 (1.16.0): nothing waiting on the staff Today page.
function emptyOverview(role: string) {
  return { role, pending_inductions: 0, pending_bookings: 0, urgent_requests: 0, waitlisted: 0, changes_waiting: 0, due_soon: [],
    due_soon_hours: 6, out_of_service: [], today: [], today_count: 0, missed_today: 0, can_decide_urgent: role === 'MANAGER' }
}

async function signIn(page: Page, role: Role = 'STUDENT') {
  if (role !== 'STUDENT') {
    // Admins and Managers use the staff sign-in page (zID + password); the account decides the role.
    await page.getByRole('link', { name: 'Staff sign-in', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Staff sign-in', exact: true })).toBeVisible()
    await page.getByLabel('Staff zID', { exact: true }).fill(users[role].zid)
    await page.getByLabel('Password', { exact: true }).fill(STAFF_PASSWORD)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByRole('button', { name: `Account options for ${users[role].display_name}` })).toBeVisible()
    return
  }
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
  { entry: '/bookings/?view=upcoming', destination: '/bookings?view=upcoming', heading: 'My bookings', menu: 'My bookings' },
  { entry: '/resources/?kind=ROOM', destination: '/resources?kind=ROOM', heading: 'Book a resource', menu: 'Book a resource' },
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
  { role: 'STUDENT', home: '/dashboard', heading: 'Dashboard', forbidden: '/admin/qualifications' },
  // Sprint 3 (1.16.0): staff start on Today.
  { role: 'ADMIN', home: '/admin/today', heading: 'Today', forbidden: '/manager/bookings' },
  { role: 'MANAGER', home: '/manager/home', heading: 'Lab overview', forbidden: '/dashboard' }, // 2026-11-07
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
    await page.getByRole('link', { name: `Go to ${heading}`, exact: true }).click()
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${home}`)
  })

  test(`${role} does not return to a forbidden anonymous deep link`, async ({ page }) => {
    await page.goto(`/#${forbidden}`)
    await signIn(page, role)
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${home}`)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  })
}

test('Manager returns to user management after mock login and can reopen it from navigation without changing roles', async ({ page, api }) => {
  await page.goto('/#/manager/users')
  await signIn(page, 'MANAGER')
  await expect(page).toHaveURL(/#\/manager\/users$/)
  await expect(page).toHaveTitle('User management · UNSW SmartLab')
  await expect(page.getByRole('heading', { name: 'User management', exact: true })).toBeVisible()
  const table = page.getByRole('table')
  await expect(table.getByRole('row')).toHaveCount(accounts.length + 1)
  await expect(table.getByRole('cell', { name: users.STUDENT.zid, exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: users.ADMIN.university_email, exact: true })).toBeVisible()
  expect(api.managerUserRequests.length).toBeGreaterThan(0)
  expect(api.managerUserRequests.every((request) => request === 'GET admin/users/')).toBe(true)
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true })
  const userManagement = navigation.getByRole('link', { name: 'User management', exact: true })
  await expect(userManagement).toHaveAttribute('aria-current', 'page')
  await navigation.getByRole('link', { name: 'Room management', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Room management', exact: true })).toBeVisible()
  api.managerUserRequests.length = 0
  await userManagement.click()
  await expect(page.getByRole('heading', { name: 'User management', exact: true })).toBeVisible()
  await expect(table.getByRole('row')).toHaveCount(accounts.length + 1)
  await expect(userManagement).toHaveAttribute('aria-current', 'page')
  await expect(page).toHaveTitle('User management · UNSW SmartLab')
  expect(api.managerUserRequests.length).toBeGreaterThan(0)
  expect(api.managerUserRequests.every((request) => request === 'GET admin/users/')).toBe(true)
})

test('staff can book too: booking, my bookings and induction pages are in the menu (client, 17 Oct)', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await expect(page).toHaveURL('http://127.0.0.1:5174/#/admin/today') // Sprint 3 (1.16.0): staff home is Today
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true })
  for (const [menu, path, heading] of [
    ['Book a resource', '/resources', 'Book a resource'],
    ['My bookings', '/bookings', 'My bookings'],
  ] as const) {
    await navigation.getByRole('link', { name: menu, exact: true }).click()
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${path}`)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  }
  await expect(navigation.getByRole('link', { name: 'Induction & training', exact: true })).toBeVisible()
  await page.goto('/#/dashboard')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
})

for (const role of ['STUDENT', 'ADMIN'] as const) {
  test(`${role} cannot enter user management or request its user data`, async ({ page, api }) => {
    await page.goto('/#/manager/users')
    await signIn(page, role)
    await expect(page).toHaveURL(role === 'STUDENT' ? /#\/dashboard$/ : /#\/admin\/today$/) // Sprint 3 (1.16.0)
    await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'User management', exact: true })).toHaveCount(0)
    expect(api.managerUserRequests).toEqual([])
    await page.goto('/#/manager/users')
    await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
    expect(api.managerUserRequests).toEqual([])
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
    await expect(page.getByRole('heading', { name: 'Page not found', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Book a resource', exact: true })).toHaveCount(0)
    await page.getByRole('link', { name: 'Go to Dashboard', exact: true }).click()
    await expect(page).toHaveURL(/#\/dashboard$/)
  }
})

test('menu navigation and browser history keep the active link in sync', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page)
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true })
  const resources = navigation.getByRole('link', { name: 'Book a resource', exact: true })
  const bookings = navigation.getByRole('link', { name: 'My bookings', exact: true })
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
  await dialog.getByRole('link', { name: 'My bookings', exact: true }).click()
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

for (const { label, user, home } of [
  { label: 'Administrator', user: users.ADMIN, home: '/admin/today' }, // Sprint 3 (1.16.0)
  { label: 'Manager', user: users.MANAGER, home: '/manager/home' }, // 2026-11-07
]) {
  test(`staff sign-in authenticates ${label} with zID and password`, async ({ page, api }) => {
    await page.goto('/#/login')
    await page.getByRole('link', { name: 'Staff sign-in', exact: true }).click()
    await expect(page).toHaveURL(/#\/staff\/login$/)
    await page.getByLabel('Staff zID', { exact: true }).fill(user.zid)
    await page.getByLabel('Password', { exact: true }).fill('wrong-password')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('zID or password is not correct')
    await page.getByLabel('Password', { exact: true }).fill(STAFF_PASSWORD)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByRole('button', { name: `Account options for ${user.display_name}` })).toBeVisible()
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${home}`)
    expect(api.loginBodies).toEqual([{ zid: user.zid, password: 'wrong-password' }, { zid: user.zid, password: STAFF_PASSWORD }])
  })
}

test('each sign-in page refuses the other kind of account', async ({ page, api }) => {
  await page.goto('/#/login/mock-sso')
  await page.getByLabel('Demo zID or university email', { exact: true }).fill(users.ADMIN.zid)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Staff sign-in page')
  // Sprint 3 (2026-10-28 feedback L1, L4): the hint links to staff sign-in, whose breadcrumb leads back.
  await page.getByRole('alert').getByRole('link', { name: 'Staff sign-in page', exact: true }).click()
  await expect(page).toHaveURL(/#\/staff\/login$/)
  await page.getByRole('link', { name: 'SmartLab', exact: true }).click()
  await expect(page).toHaveURL(/#\/login$/)
  await page.goto('/#/staff/login')
  await page.getByLabel('Staff zID', { exact: true }).fill(users.STUDENT.zid)
  await page.getByLabel('Password', { exact: true }).fill(STAFF_PASSWORD)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Students sign in with university sign-in')
  expect(api.requests).not.toContain('auth/me/')
})

test('an administrator zID and login response cannot grant a role rejected by auth/me', async ({ page, api }) => {
  api.verifiedRole = 'STUDENT'
  await page.goto('/#/admin/qualifications')
  await page.getByRole('link', { name: 'Staff sign-in', exact: true }).click()
  await page.getByLabel('Staff zID', { exact: true }).fill(users.ADMIN.zid)
  await page.getByLabel('Password', { exact: true }).fill(STAFF_PASSWORD)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/#\/dashboard$/)
  await expect(page.getByRole('button', { name: 'Account options for Test Student' })).toBeVisible()
  expect(api.loginBodies).toEqual([{ zid: users.ADMIN.zid, password: STAFF_PASSWORD }])
  expect(api.requests).toContain('auth/me/')
  expect(api.requests).not.toContain('admin/qualifications/')
  await page.goto('/#/admin/qualifications')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
})


// Sprint 3 (2026-10-25, Loy): new demo students sign up on the mock SSO page ("Create one").
test('a new demo student creates an account on the mock sign-in page', async ({ page, api }) => {
  api.config = { ...config, demo_registration_enabled: true }
  const bodies: unknown[] = []
  await page.route('**/api/v1/auth/demo-register/', async (route) => {
    bodies.push(route.request().postDataJSON())
    return route.fulfill({ status: 201, json: { access_token: `test-token-${users.STUDENT.zid}`, token_type: 'Bearer', expires_in: 3600, mode: 'demo', user: users.STUDENT } })
  })
  await page.goto('/#/login/mock-sso')
  await page.getByRole('button', { name: 'Create one', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Create account', exact: true })).toBeVisible()
  await page.getByLabel('zID', { exact: true }).fill(' Z5555555 ')
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Enter your full name and university email.')
  expect(bodies).toHaveLength(0)
  await page.getByLabel('Full name', { exact: true }).fill('New Student')
  await page.getByLabel('University email', { exact: true }).fill('z5555555@ad.unsw.edu.au')
  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(page).toHaveURL(/#\/dashboard$/)
  expect(bodies).toEqual([{ zid: 'z5555555', display_name: 'New Student', university_email: 'z5555555@ad.unsw.edu.au' }])
})

test('the mock sign-in page offers no sign-up when demo registration is off', async ({ page }) => {
  await page.goto('/#/login/mock-sso')
  await expect(page.getByLabel('Demo zID or university email')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create one', exact: true })).toHaveCount(0)
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

// Calendar Sync page (Admin and Manager): connection status and failed calendar updates, with synthetic data.
function calendarItem(id: string, overrides: Record<string, unknown> = {}, sync: Record<string, unknown> = {}) {
  return {
    booking_id: id, booking_status: 'APPROVED', start: '2030-01-10T01:00:00Z', end: '2030-01-10T02:00:00Z', urgent: false,
    resource: { id: 'room-1', name: 'Lab Room 1', location: 'Building A' },
    booked_for: { zid: 'z1000001', display_name: 'Test Student' }, booked_by: null, invited: false,
    sync: { status: 'SYNCED', action: 'CREATE', attempts: 1, last_error: null, next_attempt_at: null,
      last_success_at: '2030-01-01T00:00:00Z', web_link: null, ...sync },
    ...overrides,
  }
}

test('staff see the Outlook connection and failed calendar updates first, and can retry', async ({ page }) => {
  const calls: string[] = []
  let fixed = false
  await page.route('**/api/v1/admin/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (!path.startsWith('admin/outlook/') && !/admin\/bookings\/[^/]+\/outlook-/.test(path)) return route.fallback()
    calls.push(`${request.method()} ${path}`)
    if (path === 'admin/outlook/' && request.method() === 'GET') {
      return route.fulfill({ json: {
        enabled: true, configured: true, mode: 'delegated_token', direction: 'system_to_outlook', invite_mode: 'allowlist',
        last_check: { at: '2030-01-01T00:00:00Z', ok: true, code: null, mode: 'delegated_token', calendar_name: 'Calendar', owner: 'me@example.test' },
        summary: { total: 2, synced: fixed ? 2 : 1, pending: 0, failed: fixed ? 0 : 1 },
        items: [
          calendarItem('failed-1', { booked_for: { zid: 'z1000002', display_name: 'Failing Student' }, booked_by: { zid: 'z9000002', display_name: 'Test Manager' } },
            fixed ? {} : { status: 'FAILED', last_error: 'GRAPH_HTTP_401', attempts: 3 }),
          calendarItem('fine-1'),
        ],
      } })
    }
    if (path === 'admin/outlook/check/') {
      return route.fulfill({ json: { at: '2030-01-01T00:00:00Z', ok: false, code: 'TOKEN_EXPIRED', mode: 'delegated_token', calendar_name: null, owner: null } })
    }
    if (path === 'admin/bookings/failed-1/outlook-retry/') {
      fixed = true
      return route.fulfill({ json: { id: 'failed-1', outlook_sync: { status: 'SYNCED', action: 'CREATE', web_link: null, last_error: null } } })
    }
    return route.fulfill({ status: 500, json: { error: { code: 'UNMOCKED', message: 'Unexpected calendar request.' } } })
  })

  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Calendar sync', exact: true }).click()
  await expect(page).toHaveURL(/#\/admin\/calendar-sync$/)
  await expect(page.getByRole('status', { name: 'Outlook connection' })).toContainText('Connected to Outlook')
  await expect(page.getByRole('button', { name: 'Check Outlook for changes' })).toHaveCount(0)

  const rows = page.getByRole('table', { name: 'Calendar sync by booking' }).locator('tbody tr')
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toContainText('Failed')
  await expect(rows.nth(0)).toContainText('Microsoft sign-in expired')
  await expect(rows.nth(0)).toContainText('Booked by Test Manager (z9000002)')

  await page.getByRole('button', { name: 'Check connection', exact: true }).click()
  await expect(page.getByText('Microsoft sign-in expired. Sign in again on the server computer, then retry.').first()).toBeVisible()

  await rows.nth(0).getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText('Calendar updated.')).toBeVisible()
  await expect(rows.nth(0)).toContainText('Synced')
  expect(calls).toContain('POST admin/bookings/failed-1/outlook-retry/')
})

test('students cannot open Calendar Sync', async ({ page, api }) => {
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Calendar sync', exact: true })).toHaveCount(0)
  await page.goto('/#/admin/calendar-sync')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
  expect(api.requests.filter((path) => path.startsWith('admin/outlook'))).toEqual([])
})

// Book a Resource -> Find a free time: filters, one row per resource, click a free time to book it.
test('find a free time searches only on submit and preserves the chosen interval in booking review', async ({ page }) => {
  const room = { id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
    required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00:00', closing_time: '20:00:00',
    timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null, category: null }
  const printer = { ...room, id: 'printer-1', name: '3D Printer 001', kind: 'EQUIPMENT', location: 'Lab Room 2', room_id: 'room-2', category: 'Fabrication', required_qualification_id: 'req-2' }
  const slot = (start: string, end: string, extra: Record<string, unknown> = {}) =>
    ({ start, end, available: true, reason_code: null, hold_until: null, held_by_me: false, requested_by_me: false, ...extra })
  const queries: string[] = []
  await page.route('**/api/v1/resources/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/resources/day-overview/')) {
      queries.push(url.search)
      return route.fulfill({ json: {
        date: '2030-01-10', duration_minutes: 60, timezone: 'Australia/Sydney', earliest_date: '2030-01-10', latest_date: '2030-02-02',
        min_advance_days: 7, max_advance_days: 30, rooms: [{ id: 'room-1', name: 'Lab Room 1' }, { id: 'room-2', name: 'Lab Room 2' }],
        categories: ['Fabrication', 'Microscopy'], count: 2,
        results: [
          { resource: room, room_name: null, can_request: true, qualification_status: 'VERIFIED', resource_status: 'AVAILABLE', status_reason: null,
            slots: [slot('2030-01-09T21:00:00Z', '2030-01-09T22:00:00Z'), slot('2030-01-09T21:30:00Z', '2030-01-09T22:30:00Z', { available: false, reason_code: 'BOOKED' })] },
          { resource: printer, room_name: 'Lab Room 2', can_request: false, qualification_status: 'NOT_SUBMITTED', resource_status: 'AVAILABLE', status_reason: null,
            slots: [slot('2030-01-09T21:00:00Z', '2030-01-09T22:00:00Z'), slot('2030-01-09T21:30:00Z', '2030-01-09T22:30:00Z')] },
        ],
      } })
    }
    if (url.pathname.endsWith('/resources/room-1/availability/')) {
      return route.fulfill({ json: {
        resource_id: 'room-1', date: '2030-01-10', timezone: 'Australia/Sydney', duration_minutes: 30, can_request: true, qualification_status: 'VERIFIED',
        earliest_date: '2030-01-10', latest_date: '2030-02-02', min_advance_days: 7, max_advance_days: 30, resource_status: 'AVAILABLE', status_reason: null,
        slots: [slot('2030-01-09T21:00:00Z', '2030-01-09T21:30:00Z'), slot('2030-01-09T21:30:00Z', '2030-01-09T22:00:00Z'), slot('2030-01-09T22:00:00Z', '2030-01-09T22:30:00Z')],
      } })
    }
    return route.fallback()
  })

  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/resources')
  await page.getByRole('tab', { name: 'Find a free time', exact: true }).click()
  expect(queries).toHaveLength(0)
  await page.getByLabel('Date', { exact: true }).fill('2030-01-10')
  await page.getByLabel('Start time', { exact: true }).fill('08:00')
  expect(queries).toHaveLength(0)
  await page.getByRole('button', { name: 'Find available resources', exact: true }).click()
  await expect(page.getByRole('article', { name: 'Lab Room 1', exact: true })).toBeVisible()
  expect(queries.some((q) => q.includes('bookable_only=true'))).toBe(true)
  expect(queries.some(q => q.includes('free_at=08%3A00'))).toBe(true)
  await expect(page.getByRole('article', { name: '3D Printer 001', exact: true }).getByRole('button', { name: 'Review booking' })).toBeDisabled()

  await page.getByText('More filters', { exact: true }).click()
  const queryCount = queries.length
  await page.getByLabel('Equipment type').selectOption('Fabrication')
  expect(queries).toHaveLength(queryCount)
  await expect(page.getByRole('article', { name: 'Lab Room 1', exact: true }).getByRole('button', { name: 'Review booking' })).toBeDisabled()
  await page.getByRole('button', { name: 'Find available resources', exact: true }).click()
  await expect.poll(() => queries.some((q) => q.includes('category=Fabrication'))).toBe(true)

  await page.getByRole('article', { name: 'Lab Room 1', exact: true }).getByRole('button', { name: 'Review booking' }).click()
  await expect(page.locator('.ui-selection')).toContainText('8:00')
  await expect(page.locator('.ui-selection')).toContainText('9:00')
  await expect(page.getByRole('button', { name: 'View day availability', exact: true })).toBeVisible()
  await expect(page.locator('.bk-timeline')).toHaveCount(0)

  // Sprint 3 (review R4, R5): the dialog is named after the resource; selecting text and releasing over the backdrop keeps it open.
  const dialog = page.getByRole('dialog', { name: 'Book Lab Room 1', exact: true })
  const purpose = dialog.getByPlaceholder(/What will you use it for/)
  await purpose.fill('Thesis experiment')
  const box = (await purpose.boundingBox())!
  await page.mouse.move(box.x + 10, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(4, 4)
  await page.mouse.up()
  await expect(dialog).toBeVisible()
  await expect(purpose).toHaveValue('Thesis experiment')

  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('article', { name: 'Lab Room 1', exact: true }).getByRole('button', { name: 'Review booking' })).toBeFocused()

  // A plain click on the backdrop still closes it.
  await page.getByRole('article', { name: 'Lab Room 1', exact: true }).getByRole('button', { name: 'Review booking' }).click()
  await expect(dialog).toBeVisible()
  await page.mouse.click(4, 4)
  await expect(dialog).toHaveCount(0)
})

// Sprint 3: notifications, check-in, calendar link, weekly series.
const approvedBooking = (overrides: Record<string, unknown> = {}) => ({
  id: 'bk-1', student_id: 'test-student', resource_id: 'room-1', start: '2030-01-10T00:00:00Z', end: '2030-01-10T01:00:00Z',
  purpose: 'Lab', created_at: '2030-01-01T00:00:00Z', status: 'APPROVED', reason_code: 'MANUALLY_APPROVED', decision_reason: null,
  revision: 1, hold_until: null, review_due_at: null, reviewed_by: 'test-admin', hold_active: false, blocks_slot: true,
  booked_for: { id: 'test-student', zid: 'z1000001', display_name: 'Test Student', role: 'STUDENT' }, created_by_user: null, on_behalf: false,
  attendance: null, checked_in_at: null, check_in_open: true, check_in_opens_at: '2030-01-09T23:45:00Z', check_in_closes_at: '2030-01-10T00:30:00Z',
  series_id: null, ...overrides,
})

const additionalRoom = { id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
  required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, effective_max_booking_minutes: 180,
  selection_step_minutes: 30, opening_time: '08:00:00', closing_time: '20:00:00', timezone: 'Australia/Sydney',
  pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null }

const additionalReview = (overrides: Record<string, unknown> = {}) => ({
  approval_opens_at: '2030-01-07T22:00:00Z', approval_window_hours: 48, priority_group: 'PRIORITY',
  priority_reasons: ['NO_USE_THIS_WEEK'], queue_position: 1, can_approve: true, blocker_code: null, blocker_message: null, ...overrides,
})
const additionalBooking = (overrides: Record<string, unknown> = {}) => approvedBooking({
  id: 'extra-1', status: 'PENDING_APPROVAL', start: '2030-01-09T22:00:00Z', end: '2030-01-10T01:00:00Z',
  student: { id: users.STUDENT.id, zid: users.STUDENT.zid, display_name: users.STUDENT.display_name, university_email: users.STUDENT.university_email },
  additional_hours: true, additional_hours_reason: 'Finish the experiment', active_data_collection: false, data_collection_reason: null,
  hold_active: false, blocks_slot: false, check_in_open: false, additional_hours_review: additionalReview(), ...overrides,
})

const longBooking = (overrides: Record<string, unknown> = {}) => approvedBooking({
  id: 'long-1', status: 'PENDING_APPROVAL', start: '2030-01-09T22:00:00Z', end: '2030-01-10T02:00:00Z',
  student: { id: users.STUDENT.id, zid: users.STUDENT.zid, display_name: users.STUDENT.display_name, university_email: users.STUDENT.university_email },
  long_booking: true, long_booking_reason: 'Keep the experiment running continuously', review_due_at: '2030-01-02T00:00:00Z',
  hold_until: '2030-01-02T00:00:00Z', hold_active: true, blocks_slot: true, check_in_open: false, ...overrides,
})

for (const outcome of ['PENDING_APPROVAL', 'WAITLISTED'] as const) {
  test(`long-booking form enforces the server duration range and submits ${outcome}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
    const room = { ...additionalRoom, max_booking_minutes: 300 }
    let created: ReturnType<typeof longBooking> | null = null
    const sent: { body: Record<string, unknown>; key: string | undefined }[] = []
    await page.route('**/api/v1/**', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname.replace('/api/v1/', '')
      if (path === 'resources/') return route.fulfill({ json: { count: 2, results: [room,
        { ...room, id: 'short-room', name: 'Short room', max_booking_minutes: 180 }] } })
      if (path === 'resources/room-1/availability/') {
        const long = url.searchParams.get('long_booking') === 'true'
        expect(url.searchParams.has('additional_hours')).toBe(false)
        expect(url.searchParams.has('urgent')).toBe(false)
        const date = url.searchParams.get('date')!
        const start = Date.parse(`${date}T00:00:00Z`) - 2 * 60 * 60 * 1000
        return route.fulfill({ json: { resource_id: room.id, date, timezone: 'Australia/Sydney', duration_minutes: 30,
          long_booking: long, normal_max_booking_minutes: 180, min_booking_minutes: long ? 210 : 30,
          max_booking_minutes: long ? 300 : 180, selection_step_minutes: 30, earliest_date: '2030-01-08', latest_date: '2030-01-29',
          min_advance_days: 7, max_advance_days: 28, can_request: true, qualification_status: 'VERIFIED',
          slots: Array.from({ length: 16 }, (_, i) => ({ start: new Date(start + i * 1800000).toISOString(), end: new Date(start + (i + 1) * 1800000).toISOString(),
            available: outcome !== 'WAITLISTED' || i > 0, reason_code: outcome === 'WAITLISTED' && i === 0 ? 'BOOKED' : null,
            hold_until: null, held_by_me: false, requested_by_me: false })) } })
      }
      if (path === 'bookings/long-bookings/' && request.method() === 'POST') {
        sent.push({ body: request.postDataJSON(), key: request.headers()['idempotency-key'] })
        created = longBooking({ ...request.postDataJSON(), status: outcome, waitlist_position: outcome === 'WAITLISTED' ? 2 : null })
        return route.fulfill({ status: 201, json: created })
      }
      if (path === 'bookings/') return route.fulfill({ json: { count: created ? 1 : 0, results: created ? [created] : [] } })
      return route.fallback()
    })
    await page.goto('/#/login')
    await signIn(page)
    await page.goto('/#/resources')
    await expect(page.getByRole('button', { name: 'Request a longer booking', exact: true })).toHaveCount(1)
    await page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Lab Room 1', exact: true }) }).getByRole('button', { name: 'View availability' }).click()
    const normal = page.getByRole('dialog', { name: 'Book Lab Room 1', exact: true })
    await expect(normal.getByRole('combobox', { name: 'Length' }).locator('option').last()).toHaveText('3 h')
    await normal.getByRole('button', { name: 'Close', exact: true }).click()
    await page.getByRole('button', { name: 'Request a longer booking', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Request a longer booking: Lab Room 1' })
    await expect(dialog.getByLabel('Date', { exact: true })).toHaveValue('2030-01-08')
    await expect(dialog.getByLabel('Date', { exact: true })).toHaveAttribute('max', '2030-01-29')
    await expect(dialog.getByRole('combobox', { name: 'Length' }).locator('option').first()).toHaveText('3.5 h')
    await expect(dialog.getByRole('combobox', { name: 'Length' }).locator('option').last()).toHaveText('5 h')
    await dialog.getByLabel('Date', { exact: true }).fill('2030-01-10')
    await dialog.getByLabel('Purpose', { exact: false }).fill('Long experiment')
    await dialog.locator('.ui-tl-cell').nth(0).click()
    await expect(dialog.getByRole('alert')).toContainText('at least 3.5 h')
    await expect(dialog.getByRole('button', { name: 'Submit long-booking request' })).toBeDisabled()
    await dialog.getByRole('combobox', { name: 'Length' }).selectOption('8')
    await dialog.getByRole('combobox', { name: 'Start time' }).selectOption('0')
    await expect(dialog.getByRole('button', { name: 'Submit long-booking request' })).toBeDisabled()
    await dialog.getByLabel('Why a longer session is needed', { exact: false }).fill('Keep the experiment running continuously')
    if (outcome === 'WAITLISTED') await expect(dialog).toContainText('a Manager must approve the longer session before its review deadline')
    await dialog.getByRole('button', { name: 'Submit long-booking request' }).click()
    await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
    await expect(page.locator('.bk-bcard')).toContainText('Manager')
    await expect(page.locator('.bk-bcard')).toContainText('never approved automatically')
    if (outcome === 'PENDING_APPROVAL') await expect(page.locator('.bk-bcard')).toContainText('expires if nobody decides')
    else await expect(page.locator('.bk-bcard')).toContainText('#2')
    expect(sent).toHaveLength(1)
    expect(sent[0].key).toBeTruthy()
    expect(sent[0].body).toEqual({ resource_id: room.id, start: '2030-01-09T22:00:00.000Z', end: '2030-01-10T02:00:00.000Z',
      purpose: 'Long experiment', long_booking_reason: 'Keep the experiment running continuously' })
  })
}

for (const role of ['ADMIN', 'MANAGER'] as const) {
  test(`long-booking review restricts decisions for ${role}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
    let requests = [longBooking(), longBooking({ id: 'own-long', created_by: users[role].id })]
    const decisions: Record<string, unknown>[] = []
    await page.route('**/api/v1/**', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname.replace('/api/v1/', '')
      if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
      if (path === 'admin/bookings/') return route.fulfill({ json: { count: requests.length, results: url.searchParams.get('status') === 'PENDING_APPROVAL' ? requests : [] } })
      if (path === 'admin/bookings/long-1/review/') {
        decisions.push(request.postDataJSON())
        requests = requests.filter(item => item.id !== 'long-1')
        return route.fulfill({ json: longBooking({ status: 'APPROVED' }) })
      }
      return route.fallback()
    })
    await page.goto('/#/login')
    await signIn(page, role)
    await page.goto('/#/admin/bookings?type=long-bookings')
    await expect(page.getByRole('tab', { name: /Long bookings/ })).toHaveAttribute('aria-selected', 'true')
    const rows = page.locator('tbody tr')
    await expect(rows).toHaveCount(2)
    const own = rows.filter({ hasText: 'You created this request' })
    await expect(own).toHaveCount(1)
    await expect(own.getByRole('button', { name: /Approve|Reject/ })).toHaveCount(0)
    if (role === 'ADMIN') {
      await expect(page.getByText('Longer booking: a Manager decides', { exact: true })).toBeVisible()
      await expect(rows.getByRole('button', { name: /Approve|Reject/ })).toHaveCount(0)
    } else {
      await rows.getByRole('button', { name: '✓ Approve', exact: true }).click()
      await expect(rows).toHaveCount(1)
      expect(decisions).toEqual([{ decision: 'APPROVED', reason: '' }])
    }
  })
}

test('approved longer bookings require cancellation and a new request to change time', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1/', '')
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
    if (path === 'bookings/') return route.fulfill({ json: { count: 1, results: [longBooking({ status: 'APPROVED', student_id: users.MANAGER.id })] } })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/bookings')
  await expect(page.locator('.bk-bcard')).toContainText('cancel and submit a new long-booking request')
  await expect(page.getByRole('button', { name: /^(Change time|Reschedule)$/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Cancel booking', exact: true })).toBeVisible()
})

test('additional hours can be requested in advance with a reason, normal duration cap and retry-safe submission', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
  const sent: { body: Record<string, unknown>; key: string | undefined }[] = []
  const availabilityModes: boolean[] = []
  let created: ReturnType<typeof additionalBooking> | null = null
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1/', '')
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
    if (path === 'resources/room-1/availability/') {
      const additional = url.searchParams.get('additional_hours') === 'true'
      availabilityModes.push(additional)
      const date = url.searchParams.get('date')!
      const start = Date.parse(`${date}T00:00:00Z`) - 2 * 60 * 60 * 1000
      return route.fulfill({ json: { resource_id: 'room-1', date, timezone: 'Australia/Sydney', duration_minutes: 30,
        max_booking_minutes: 180, selection_step_minutes: 30, earliest_date: additional ? '2030-01-01' : '2030-01-08',
        latest_date: '2030-01-29', min_advance_days: additional ? 0 : 7, max_advance_days: 28,
        can_request: true, qualification_status: 'VERIFIED', additional_hours: additional, additional_hours_approval_window_hours: 72,
        slots: Array.from({ length: 16 }, (_, i) => ({ start: new Date(start + i * 1800000).toISOString(), end: new Date(start + (i + 1) * 1800000).toISOString(),
          available: !additional || i > 0, reason_code: additional && i === 0 ? 'BOOKED' : null, hold_until: null, held_by_me: false, requested_by_me: false })) } })
    }
    if (path === 'bookings/additional-hours/' && request.method() === 'POST') {
      const body = request.postDataJSON()
      sent.push({ body, key: request.headers()['idempotency-key'] })
      if (sent.length === 1) return route.fulfill({ status: 503, json: { error: { code: 'TEMPORARILY_UNAVAILABLE', message: 'Temporary interruption. Try again.' } } })
      created = additionalBooking({ ...body, additional_hours_review: additionalReview({ approval_opens_at: '2030-01-06T22:00:00Z', approval_window_hours: 72,
        can_approve: false, blocker_code: 'ADDITIONAL_HOURS_TOO_EARLY', blocker_message: 'Approval has not opened yet.' }) })
      return route.fulfill({ status: 201, json: created })
    }
    if (path === 'bookings/') return route.fulfill({ json: { count: created ? 1 : 0, results: created ? [created] : [] } })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page)
  await page.goto('/#/resources')
  await page.getByRole('button', { name: 'View availability', exact: true }).click()
  const normal = page.getByRole('dialog', { name: 'Book Lab Room 1', exact: true })
  await expect(normal.getByRole('combobox', { name: 'Length', exact: true }).locator('option').last()).toHaveText('3 h')
  await normal.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Request additional hours', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Request additional hours: Lab Room 1' })
  await expect(dialog).toContainText('Approval opens 72 hours before the requested start.')
  await expect(dialog).toContainText('Pending requests do not reserve or hold the time')
  await dialog.getByLabel('Date', { exact: true }).fill('2030-01-10')
  await expect(dialog.getByRole('combobox', { name: 'Length', exact: true }).locator('option').last()).toHaveText('3 h')
  await dialog.getByRole('combobox', { name: 'Length', exact: true }).selectOption('6')
  await dialog.getByRole('combobox', { name: 'Start time', exact: true }).selectOption('0')
  await expect(dialog).toContainText('A Manager can approve only if capacity becomes available')
  await dialog.getByLabel('Purpose', { exact: false }).fill('Data collection')
  const submit = dialog.getByRole('button', { name: 'Submit additional-hours request', exact: true })
  await expect(submit).toBeDisabled()
  await dialog.getByLabel('Why additional hours are needed', { exact: false }).fill('Finish the experiment')
  await dialog.getByRole('checkbox', { name: 'I am currently collecting data' }).check()
  await expect(submit).toBeDisabled()
  await dialog.getByLabel('Describe the active data collection', { exact: false }).fill('Recording the same sample continuously')
  await submit.click()
  await expect(dialog.getByRole('alert')).toContainText('Temporary interruption')
  await submit.click()
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
  await expect(page.locator('.bk-bcard')).toContainText('Waiting for Manager approval')
  await expect(page.locator('.bk-bcard')).toContainText('does not hold the time and is never approved automatically')
  expect(sent).toHaveLength(2)
  expect(sent[0].key).toBeTruthy()
  expect(sent[1]).toEqual(sent[0])
  expect(sent[1].body).toMatchObject({ purpose: 'Data collection', additional_hours_reason: 'Finish the experiment', active_data_collection: true,
    data_collection_reason: 'Recording the same sample continuously', start: '2030-01-09T22:00:00.000Z', end: '2030-01-10T01:00:00.000Z' })
  expect(availabilityModes).toContain(false)
  expect(availabilityModes).toContain(true)
})

test('additional hours on behalf uses the checked researcher and retains the approval rules', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
  const sent: Record<string, unknown>[] = []
  const recipients: (string | null)[] = []
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1/', '')
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
    if (path === 'people/lookup/') return route.fulfill({ json: users.STUDENT })
    if (path === 'resources/room-1/availability/') {
      recipients.push(url.searchParams.get('for_zid'))
      expect(url.searchParams.get('additional_hours')).toBe('true')
      return route.fulfill({ json: { resource_id: 'room-1', date: '2030-01-01', timezone: 'Australia/Sydney', duration_minutes: 30,
        max_booking_minutes: 180, selection_step_minutes: 30, earliest_date: '2030-01-01', latest_date: '2030-01-29', min_advance_days: 0, max_advance_days: 28,
        can_request: true, qualification_status: 'VERIFIED', additional_hours: true, additional_hours_approval_window_hours: 48,
        slots: [{ start: '2030-01-01T01:00:00Z', end: '2030-01-01T01:30:00Z', available: true, reason_code: null,
          hold_until: null, held_by_me: false, requested_by_me: false }] } })
    }
    if (path === 'bookings/additional-hours/' && request.method() === 'POST') {
      sent.push(request.postDataJSON())
      return route.fulfill({ status: 201, json: additionalBooking({ ...request.postDataJSON(), on_behalf: true, created_by: users.ADMIN.id }) })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.goto('/#/resources')
  await page.getByRole('button', { name: 'Request additional hours', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Request additional hours: Lab Room 1' })
  await dialog.getByRole('radio', { name: 'Someone else', exact: true }).check()
  await expect(dialog.getByRole('button', { name: 'Submit additional-hours request' })).toBeDisabled()
  await dialog.getByLabel('zID of the person to book for').fill(users.STUDENT.zid)
  await dialog.getByRole('button', { name: 'Check zID', exact: true }).click()
  await expect(dialog).toContainText('Requesting for Test Student')
  await expect(dialog.getByLabel('Date', { exact: true })).toHaveAttribute('max', '2030-01-29')
  await dialog.getByRole('combobox', { name: 'Length', exact: true }).selectOption('1')
  await dialog.getByRole('combobox', { name: 'Start time', exact: true }).selectOption('0')
  await dialog.getByLabel('Purpose', { exact: false }).fill('Supervised experiment')
  await dialog.getByLabel('Why additional hours are needed', { exact: false }).fill('Extra sample to measure')
  await dialog.getByRole('button', { name: 'Submit additional-hours request' }).click()
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
  expect(recipients.at(-1)).toBe(users.STUDENT.zid)
  expect(sent).toEqual([expect.objectContaining({ on_behalf_of_zid: users.STUDENT.zid, active_data_collection: false,
    additional_hours_reason: 'Extra sample to measure', purpose: 'Supervised experiment' })])
  expect(sent[0]).not.toHaveProperty('data_collection_reason')
})

for (const kind of ['additional-hours', 'long-booking'] as const) {
test(`${kind} lookup ignores an old researcher response after the zID changes`, async ({ page }) => {
  const isLong = kind === 'long-booking'
  const entry = isLong ? 'Request a longer booking' : 'Request additional hours'
  const endpoint = isLong ? 'bookings/long-bookings/' : 'bookings/additional-hours/'
  await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
  let releaseA!: () => void
  let releaseB!: () => void
  const gateA = new Promise<void>(resolve => { releaseA = resolve })
  const gateB = new Promise<void>(resolve => { releaseB = resolve })
  const lookups: string[] = []
  const recipients: (string | null)[] = []
  const sent: Record<string, unknown>[] = []
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1/', '')
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
    if (path === 'people/lookup/') {
      const zid = url.searchParams.get('zid')!
      lookups.push(zid)
      await (zid === users.STUDENT.zid ? gateA : gateB)
      return route.fulfill({ json: zid === users.STUDENT.zid ? users.STUDENT : unqualifiedStudent })
    }
    if (path === 'resources/room-1/availability/') {
      recipients.push(url.searchParams.get('for_zid'))
      return route.fulfill({ json: { resource_id: 'room-1', date: '2030-01-01', timezone: 'Australia/Sydney', duration_minutes: 30,
        max_booking_minutes: isLong ? 480 : 180, min_booking_minutes: isLong ? 210 : 30, selection_step_minutes: 30, earliest_date: '2030-01-01', latest_date: '2030-01-29', min_advance_days: 0, max_advance_days: 28,
        can_request: true, qualification_status: 'VERIFIED', additional_hours: !isLong, long_booking: isLong, additional_hours_approval_window_hours: 48,
        slots: Array.from({ length: 16 }, (_, i) => ({ start: new Date(Date.parse('2030-01-01T01:00:00Z') + i * 1800000).toISOString(),
          end: new Date(Date.parse('2030-01-01T01:00:00Z') + (i + 1) * 1800000).toISOString(), available: true, reason_code: null,
          hold_until: null, held_by_me: false, requested_by_me: false })) } })
    }
    if (path === endpoint && request.method() === 'POST') {
      sent.push(request.postDataJSON())
      return route.fulfill({ status: 201, json: (isLong ? longBooking : additionalBooking)({ ...request.postDataJSON(), on_behalf: true }) })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.goto('/#/resources')
  await page.getByRole('button', { name: entry, exact: true }).click()
  const dialog = page.getByRole('dialog', { name: `${entry}: Lab Room 1` })
  await dialog.getByRole('radio', { name: 'Someone else', exact: true }).check()
  const input = dialog.getByLabel('zID of the person to book for')
  await input.fill(users.STUDENT.zid)
  await dialog.getByRole('button', { name: 'Check zID', exact: true }).click()
  await expect.poll(() => lookups).toEqual([users.STUDENT.zid])
  await input.fill(unqualifiedStudent.zid)
  await dialog.getByRole('button', { name: 'Check zID', exact: true }).click()
  await expect.poll(() => lookups).toEqual([users.STUDENT.zid, unqualifiedStudent.zid])
  const staleResponse = page.waitForResponse(response => response.url().includes(`people/lookup/?zid=${users.STUDENT.zid}`))
  releaseA()
  await (await staleResponse).finished()
  // Fill unrelated fields after the stale response so React has rendered it before checking identity.
  await dialog.getByLabel('Purpose', { exact: false }).fill('Supervised experiment')
  await dialog.getByLabel(isLong ? 'Why a longer session is needed' : 'Why additional hours are needed', { exact: false }).fill('Extra sample to measure')
  await expect(input).toHaveValue(unqualifiedStudent.zid)
  await expect(dialog.getByRole('button', { name: 'Checking…', exact: true })).toBeDisabled()
  await expect(dialog.getByText(`Requesting for ${users.STUDENT.display_name}`, { exact: false })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: `Submit ${kind} request` })).toBeDisabled()
  expect(recipients).not.toContain(users.STUDENT.zid)
  expect(sent).toHaveLength(0)
  releaseB()
  await expect(dialog.getByText(`Requesting for ${unqualifiedStudent.display_name} (${unqualifiedStudent.zid})`, { exact: true })).toBeVisible()
  await dialog.getByRole('combobox', { name: 'Length', exact: true }).selectOption(isLong ? '7' : '1')
  await dialog.getByRole('combobox', { name: 'Start time', exact: true }).selectOption('0')
  await dialog.getByRole('button', { name: `Submit ${kind} request` }).click()
  await expect(page.getByRole('heading', { name: 'My bookings', exact: true })).toBeVisible()
  expect(sent).toEqual([expect.objectContaining({ on_behalf_of_zid: unqualifiedStudent.zid })])
})
}

test('additional-hours requests are visible to Admins but only Managers can decide', async ({ page }) => {
  const booking = additionalBooking({ active_data_collection: true, data_collection_reason: 'Continuous sample recording', additional_hours_review: additionalReview({ priority_reasons: ['ACTIVE_DATA_COLLECTION'] }) })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/v1/', '')
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
    if (path === 'admin/bookings/') return route.fulfill({ json: { count: url.searchParams.get('status') === 'PENDING_APPROVAL' ? 1 : 0,
      results: url.searchParams.get('status') === 'PENDING_APPROVAL' ? [booking] : [] } })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.goto('/#/admin/bookings?type=additional-hours')
  await expect(page.getByRole('tab', { name: /Additional hours/ })).toHaveAttribute('aria-selected', 'true')
  const row = page.locator('tbody tr').filter({ hasText: 'Additional hours' })
  await expect(row).toContainText('Additional hours: a Manager decides')
  await expect(row.getByRole('button', { name: /Approve|Reject/ })).toHaveCount(0)
  await row.getByRole('button', { name: 'Details' }).click()
  await expect(page.getByText('Continuous sample recording', { exact: true })).toBeVisible()
  await expect(page.getByText('No time is held. Never approved automatically; expires at the requested start.', { exact: true })).toBeVisible()
})

test('additional-hours Manager review shows queue blockers and explicitly confirms active data collection', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-08T00:00:00Z'))
  let requests = [
    additionalBooking({ id: 'standard', created_at: '2030-01-01T00:00:00Z', additional_hours_review: additionalReview({ priority_group: 'STANDARD', priority_reasons: [], queue_position: 3, can_approve: false,
      blocker_code: 'ADDITIONAL_HOURS_TOO_EARLY', blocker_message: 'Approval has not opened yet.' }) }),
    additionalBooking({ id: 'unused', created_at: '2030-01-01T02:00:00Z', additional_hours_review: additionalReview({ queue_position: 2, can_approve: false,
      blocker_code: 'ADDITIONAL_HOURS_QUEUE_PRIORITY', blocker_message: 'An earlier priority request must be decided first.' }) }),
    additionalBooking({ id: 'collecting', created_at: '2030-01-01T01:00:00Z', active_data_collection: true, data_collection_reason: 'Continuous sample recording',
      additional_hours_review: additionalReview({ priority_reasons: ['ACTIVE_DATA_COLLECTION'] }) }),
    additionalBooking({ id: 'capacity', created_at: '2030-01-01T03:00:00Z', additional_hours_review: additionalReview({ priority_group: 'STANDARD', priority_reasons: [], queue_position: 4, can_approve: false,
      blocker_code: 'ADDITIONAL_HOURS_NO_CAPACITY', blocker_message: 'No spare capacity is available for this time.' }) }),
    additionalBooking({ id: 'own', created_at: '2030-01-01T04:00:00Z', created_by: users.MANAGER.id,
      additional_hours_review: additionalReview({ priority_group: 'STANDARD', priority_reasons: [], queue_position: 5 }) }),
  ]
  const decisions: { id: string; body: Record<string, unknown> }[] = []
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1/', '')
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
    if (path === 'admin/bookings/') return route.fulfill({ json: { count: requests.length, results: url.searchParams.get('status') === 'PENDING_APPROVAL' ? requests : [] } })
    if (/^admin\/bookings\/[^/]+\/review\/$/.test(path)) {
      const id = path.split('/')[2]
      decisions.push({ id, body: request.postDataJSON() })
      requests = requests.filter(item => item.id !== id)
      return route.fulfill({ json: additionalBooking({ id, status: request.postDataJSON().decision }) })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/admin/bookings?type=additional-hours')
  const rows = page.locator('tbody tr')
  await expect(rows).toHaveCount(5)
  await expect(rows.nth(0)).toContainText('Active data collection (Manager confirmation required)')
  await expect(rows.nth(1)).toContainText('No recorded lab use this week')
  await expect(rows.nth(1).getByRole('button', { name: '✓ Approve' })).toBeDisabled()
  await expect(rows.nth(2)).toContainText('Approval has not opened yet.')
  await expect(rows.nth(2).getByRole('button', { name: '✓ Approve' })).toBeDisabled()
  await expect(rows.nth(3)).toContainText('No spare capacity')
  await expect(rows.nth(3).getByRole('button', { name: '✓ Approve' })).toBeDisabled()
  await expect(rows.nth(4)).toContainText('You created this request')
  await expect(rows.nth(4).getByRole('button', { name: /Approve|Reject/ })).toHaveCount(0)
  await rows.nth(0).getByRole('button', { name: '✓ Approve' }).click()
  const approval = page.getByRole('dialog', { name: 'Approve additional hours?', exact: true })
  await expect(approval).toContainText('Continuous sample recording')
  await expect(approval).toContainText('you confirm this researcher is currently collecting data')
  expect(decisions).toHaveLength(0)
  await approval.getByRole('button', { name: 'Confirm data collection and approve' }).click()
  await expect(rows).toHaveCount(4)
  expect(decisions[0]).toEqual({ id: 'collecting', body: { decision: 'APPROVED', reason: '', confirm_active_data_collection: true } })
  await rows.filter({ hasText: 'Approval has not opened yet.' }).getByRole('button', { name: '✕ Reject' }).click()
  const rejection = page.getByRole('dialog', { name: 'Reject this request?', exact: true })
  await rejection.getByLabel('Reason (shown to the student)').fill('Please choose a different session')
  await rejection.getByRole('button', { name: 'Reject request' }).click()
  await expect(rows).toHaveCount(3)
  expect(decisions[1]).toEqual({ id: 'standard', body: { decision: 'REJECTED', reason: 'Please choose a different session' } })
})

for (const role of ['STUDENT', 'MANAGER'] as const) {
  test(`approved additional hours cannot be moved by ${role}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1/', '')
      if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [additionalRoom] } })
      if (path === 'bookings/') return route.fulfill({ json: { count: 1, results: [additionalBooking({ status: 'APPROVED', student_id: users[role].id })] } })
      return route.fallback()
    })
    await page.goto('/#/login')
    await signIn(page, role)
    await page.goto('/#/bookings')
    await expect(page.locator('.bk-bcard')).toContainText('cancel and submit a new request')
    await expect(page.getByRole('button', { name: /^(Change time|Reschedule)$/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Cancel booking', exact: true })).toBeVisible()
  })
}

test('test account 1 has verified inductions without an evidence upload form', async ({ page }) => {
  const requirements = [
    { id: 'general', name: 'General induction', description: '', prerequisite_ids: [] },
    { id: 'advanced', name: 'Advanced induction', description: '', prerequisite_ids: ['general'] },
  ]
  const qualifications = requirements.map(requirement => ({ id: `grant-${requirement.id}`, student_id: 'test-student',
    requirement_id: requirement.id, title: 'Automatic test-account access', notes: '', file_id: '', file_url: '',
    submitted_at: '2026-01-01T00:00:00Z', status: 'VERIFIED', effective_status: 'VERIFIED', valid_until: null }))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1/', '')
    if (path === 'auth/me/') return route.fulfill({ json: { ...users.STUDENT, zid: '1', test_account: true, bypass_booking_rules: false } })
    if (path === 'qualification-requirements/') return route.fulfill({ json: { count: 2, results: requirements } })
    if (path === 'qualifications/') return route.fulfill({ json: { count: 2, results: qualifications } })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/induction')
  await expect(page.locator('.ind-list .ui-pill')).toHaveText(['Verified', 'Verified'])
  await expect(page.getByText('All inductions are automatically verified for test account 1. No evidence upload is required.', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Submit induction evidence', exact: true })).toHaveCount(0)
  await expect(page.locator('input[type=file]')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /^(Upload|Re-upload)$/ })).toHaveCount(0)
})

test('the bell shows unread notifications and opens the linked page', async ({ page }) => {
  const read: string[] = []
  await page.route('**/api/v1/notifications/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'notifications/' && request.method() === 'GET') {
      return route.fulfill({ json: { count: 2, unread_count: read.length ? 0 : 1, results: [
        { id: 'n1', recipient_id: 'test-student', kind: 'BOOKING_APPROVED', title: 'Booking approved', body: 'Lab Room 1 on Thu 10 Jan was approved.',
          created_at: '2030-01-01T00:00:00Z', link: '/bookings', booking_id: 'bk-1', read_at: read.length ? '2030-01-01T00:01:00Z' : null },
        { id: 'n2', recipient_id: 'test-student', kind: 'QUALIFICATION_VERIFIED', title: 'Induction approved', body: 'Your evidence was approved.',
          created_at: '2029-12-31T00:00:00Z', link: '/induction', booking_id: null, read_at: '2030-01-01T00:00:00Z' },
      ] } })
    }
    if (path === 'notifications/n1/read/' && request.method() === 'POST') {
      read.push('n1')
      return route.fulfill({ json: { id: 'n1', read_at: '2030-01-01T00:01:00Z' } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  const bell = page.getByRole('button', { name: 'Notifications, 1 unread' })
  await expect(bell).toBeVisible()
  await bell.click()
  const panel = page.getByRole('region', { name: 'Notifications' })
  await expect(panel).toContainText('Booking approved')
  await expect(panel).toContainText('Induction approved')
  await panel.getByRole('button', { name: /Booking approved/ }).click()
  await expect(page).toHaveURL(/#\/bookings$/)
  expect(read).toEqual(['n1'])
  await expect(page.getByRole('button', { name: 'Notifications', exact: true })).toBeVisible()
})

// Sprint 3 (1.15.0): the badge used to inherit 27px from ".app-icon-button > span" and covered the bell.
test('the bell badge stays small, and the panel groups notifications with an icon each', async ({ page }) => {
  const now = new Date()
  const earlier = new Date(now.getTime() - 3 * 86400000)
  await page.route('**/api/v1/notifications/**', (route) => route.fulfill({ json: { count: 2, unread_count: 4, results: [
    { id: 'n1', recipient_id: 'test-student', kind: 'BOOKING_REJECTED', title: 'Booking request rejected', body: 'Lab Room 1 was rejected.',
      created_at: now.toISOString(), link: '/bookings', booking_id: 'bk-1', read_at: null },
    { id: 'n2', recipient_id: 'test-student', kind: 'BOOKING_REMINDER', title: 'Booking tomorrow', body: 'Lab Room 1 starts tomorrow.',
      created_at: earlier.toISOString(), link: '/bookings', booking_id: 'bk-2', read_at: now.toISOString() },
  ] } }))
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  const bell = page.getByRole('button', { name: 'Notifications, 4 unread' })
  const badge = bell.locator('.nt-badge')
  await expect(badge).toHaveText('4')
  await expect(badge).toHaveCSS('font-size', '12px') // Sprint 3 (internal-tool UI, AI-3): nothing below 12px
  // Measure after the pop animation, which briefly scales the badge to 115%.
  await badge.evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)))
  const box = await badge.boundingBox()
  expect(box!.height).toBeLessThanOrEqual(20)
  await bell.click()
  const panel = page.getByRole('region', { name: 'Notifications' })
  await expect(panel.getByRole('region', { name: 'Today' })).toContainText('Booking request rejected')
  await expect(panel.getByRole('region', { name: 'Earlier' })).toContainText('Booking tomorrow')
  await expect(panel.locator('.nt-icon.is-cross')).toHaveCount(1)
  await expect(panel.locator('.nt-icon.is-clock')).toHaveCount(1)
  await expect(panel.getByRole('button', { name: /Booking request rejected.*Unread/ })).toBeVisible()
})

test('my bookings: check in, and get the calendar subscription link', async ({ page }) => {
  let checkedIn = false
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'bookings/' && request.method() === 'GET') {
      return route.fulfill({ json: { count: 1, results: [checkedIn
        ? approvedBooking({ attendance: 'CHECKED_IN', check_in_open: false }) : approvedBooking()] } })
    }
    if (path === 'bookings/bk-1/check-in/' && request.method() === 'POST') {
      checkedIn = true
      return route.fulfill({ json: approvedBooking({ attendance: 'CHECKED_IN', check_in_open: false }) })
    }
    if (path === 'calendar/link/') return route.fulfill({ json: { path: '/api/v1/calendar/secret-token-1234567890.ics', created_at: '2030-01-01T00:00:00Z' } })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/bookings')
  await page.getByRole('button', { name: "I'm here", exact: true }).click()
  await expect(page.getByText('Checked in', { exact: true }).first()).toBeVisible()
  expect(checkedIn).toBe(true)
  await page.getByRole('button', { name: 'Subscribe in calendar', exact: true }).click()
  await expect(page.getByLabel('Calendar subscription link')).toHaveValue(/\/api\/v1\/calendar\/secret-token-1234567890\.ics$/)
})

test('booking status tabs filter locally and retain the selected view after reload', async ({ page }) => {
  let bookingReads = 0
  const future = { start: '2099-01-10T00:00:00Z', end: '2099-01-10T01:00:00Z', check_in_open: false }
  await page.route('**/api/v1/bookings/', async route => {
    bookingReads++
    return route.fulfill({ json: { count: 4, results: [
      approvedBooking({ ...future, id: 'future', purpose: 'Future session' }),
      approvedBooking({ ...future, id: 'pending', purpose: 'Pending session', status: 'PENDING_APPROVAL' }),
      approvedBooking({ ...future, id: 'cancelled', purpose: 'Cancelled session', status: 'CANCELLED' }),
      approvedBooking({ id: 'past', purpose: 'Past session', start: '2020-01-10T00:00:00Z', end: '2020-01-10T01:00:00Z', check_in_open: false }),
    ] } })
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/bookings')
  await expect(page.locator('.bk-bcard')).toHaveCount(4)
  const reads = bookingReads
  for (const [tab, purpose] of [['Upcoming', 'Future session'], ['Pending', 'Pending session'], ['Past', 'Past session'], ['Cancelled', 'Cancelled session']]) {
    await page.getByRole('tab', { name: `${tab} 1`, exact: true }).click()
    await expect(page.locator('.bk-bcard')).toHaveCount(1)
    await expect(page.locator('.bk-bcard')).toContainText(purpose)
  }
  expect(bookingReads).toBe(reads)
  await expect(page).toHaveURL(/view=cancelled$/)
  await page.reload()
  await expect(page.getByRole('tab', { name: 'Cancelled 1', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.bk-bcard')).toContainText('Cancelled session')
})

// Sprint 3 (1.20.0): resource and status filters compose without another API read.
for (const role of ['STUDENT', 'ADMIN', 'MANAGER'] as const) {
  test(`booking history resource filter composes and survives reload: ${role}`, async ({ page }) => {
    let reads = 0
    const rooms = ['room-1', 'room-2', 'room-empty'].map((id, i) => ({ id, name: `Lab Room ${i + 1}`, kind: 'ROOM', active: true }))
    await page.route('**/api/v1/resources/**', route => route.fulfill({ json: { count: rooms.length, results: rooms } }))
    await page.route('**/api/v1/bookings/', route => {
      reads++
      return route.fulfill({ json: { count: 3, results: [
        approvedBooking({ id: 'a', resource_id: 'room-1', purpose: 'First future', start: '2099-01-10T00:00:00Z', end: '2099-01-10T01:00:00Z', check_in_open: false }),
        approvedBooking({ id: 'b', resource_id: 'room-2', purpose: 'Second future', start: '2099-01-10T00:00:00Z', end: '2099-01-10T01:00:00Z', check_in_open: false }),
        approvedBooking({ id: 'c', resource_id: 'room-1', purpose: 'First past', start: '2020-01-10T00:00:00Z', end: '2020-01-10T01:00:00Z', check_in_open: false }),
      ] } })
    })
    await page.goto('/#/login')
    await signIn(page, role)
    await page.goto('/#/bookings')
    await expect(page.locator('.bk-bcard')).toHaveCount(3)
    const initialReads = reads
    await page.getByRole('combobox', { name: 'Resource', exact: true }).selectOption('room-1')
    await expect(page.locator('.bk-bcard')).toHaveCount(2)
    await page.getByRole('tab', { name: 'Past 1', exact: true }).click()
    await expect(page.locator('.bk-bcard')).toHaveCount(1)
    await expect(page.locator('.bk-bcard')).toContainText('First past')
    expect(reads).toBe(initialReads)
    await page.reload()
    await expect(page.getByRole('combobox', { name: 'Resource', exact: true })).toHaveValue('room-1')
    await expect(page.getByRole('tab', { name: 'Past 1', exact: true })).toHaveAttribute('aria-selected', 'true')
    await page.getByRole('combobox', { name: 'Resource', exact: true }).selectOption('room-empty')
    await expect(page.getByText('No bookings match these filters.')).toBeVisible()
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
    await expect(page.locator('.bk-bcard')).toHaveCount(3)
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    }
    if (role === 'STUDENT') await page.screenshot({ path: '../../output/booking-history-2026-10-28/my-bookings-390.png', fullPage: true })
  })

  test(`booking history removal confirms, keeps failed rows and persists: ${role}`, async ({ page }) => {
    let removed = false
    let fail = true
    const historical = approvedBooking({ id: 'history', start: '2020-01-10T00:00:00Z', end: '2020-01-10T01:00:00Z', check_in_open: false, purpose: 'Completed practical' })
    const future = approvedBooking({ id: 'live', start: '2099-01-10T00:00:00Z', end: '2099-01-10T01:00:00Z', check_in_open: false, purpose: 'Future practical' })
    await page.route('**/api/v1/bookings/', route => route.fulfill({ json: { count: removed ? 1 : 2, results: removed ? [future] : [historical, future] } }))
    await page.route('**/api/v1/bookings/history/remove-from-history/', route => {
      expect(route.request().method()).toBe('POST')
      expect(route.request().postDataJSON()).toEqual({})
      if (fail) return route.fulfill({ status: 503, json: { error: { code: 'UNAVAILABLE', message: 'Try again later.' } } })
      removed = true
      return route.fulfill({ status: 204 })
    })
    await page.goto('/#/login')
    await signIn(page, role)
    await page.goto('/#/bookings')
    await expect(page.getByRole('button', { name: 'Remove from my history', exact: true })).toHaveCount(1)
    const remove = () => page.getByRole('button', { name: 'Remove from my history', exact: true }).click()
    await remove()
    let dialog = page.getByRole('dialog', { name: 'Remove from your history?' })
    await expect(dialog).toContainText('Staff records and reports are kept.')
    await dialog.getByRole('button', { name: 'Keep it', exact: true }).click()
    expect(removed).toBe(false)
    await remove()
    dialog = page.getByRole('dialog', { name: 'Remove from your history?' })
    await dialog.getByRole('button', { name: 'Remove from my history', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('Try again later.')
    await expect(page.locator('.bk-bcard')).toHaveCount(2)
    fail = false
    await remove()
    await page.getByRole('dialog').getByRole('button', { name: 'Remove from my history', exact: true }).click()
    await expect(page.locator('.bk-bcard')).toHaveCount(1)
    await expect(page.locator('.bk-bcard')).toContainText('Future practical')
    await page.reload()
    await expect(page.locator('.bk-bcard')).toHaveCount(1)
    expect(removed).toBe(true)
  })
}

test('booking history removes one series date and preserves the next date', async ({ page }) => {
  let removed = false
  const rows = [
    approvedBooking({ id: 'old-date', series_id: 'weekly', start: '2020-01-10T00:00:00Z', end: '2020-01-10T01:00:00Z', check_in_open: false }),
    approvedBooking({ id: 'next-date', series_id: 'weekly', start: '2099-01-10T00:00:00Z', end: '2099-01-10T01:00:00Z', check_in_open: false }),
  ]
  await page.route('**/api/v1/bookings/', route => route.fulfill({ json: { count: removed ? 1 : 2, results: removed ? rows.slice(1) : rows } }))
  await page.route('**/api/v1/bookings/old-date/remove-from-history/', route => { removed = true; return route.fulfill({ status: 204 }) })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/bookings')
  await page.getByRole('button', { name: 'Show dates (2)', exact: true }).click()
  await page.getByRole('button', { name: 'Remove from my history', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Remove from my history', exact: true }).click()
  await expect(page.getByRole('list', { name: 'Series dates' }).getByRole('listitem')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Cancel this date', exact: true })).toBeVisible()
})

test('booking dashboard uses distinct metrics and a compact next session on desktop and phone', async ({ page }) => {
  const bookings = [10, 11, 12].map(day => approvedBooking({ id: `next-${day}`, resource_id: 'room-1',
    start: `2099-01-${day}T00:00:00Z`, end: `2099-01-${day}T01:00:00Z`, check_in_open: false }))
  await page.route('**/api/v1/dashboard/', route => route.fulfill({ json: { ...dashboard, bookings, counts: { ...dashboard.counts, APPROVED: 3 } } }))
  await page.route('**/api/v1/resources/**', route => route.fulfill({ json: { count: 1, results: [{ id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', active: true, location: 'Demo laboratory' }] } }))
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.setViewportSize({ width: 1440, height: 1000 })
  const metrics = page.locator('.dash-stats .dash-stat')
  await expect(metrics).toHaveCount(4)
  // 2026-11-03: hours left this week, with the way to ask for more.
  await expect(metrics.nth(3)).toContainText('Hours left this week')
  await expect(metrics.nth(3)).toContainText('4.5 h')
  await expect(metrics.nth(3)).toContainText('7.5 of 12 h booked')
  await expect(page.locator('.dash-more-hours')).toContainText('Need more than 12 h this week?')
  await expect(page.getByRole('link', { name: 'Request additional hours' })).toHaveAttribute('href', '#/resources')
  expect(await metrics.first().evaluate(el => getComputedStyle(el).borderRadius)).not.toBe('0px')
  expect((await page.locator('.dash-session').boundingBox())!.height).toBeLessThan(240)
  await expect(page.getByRole('heading', { name: 'More upcoming', exact: true })).toBeVisible()
  await expect(page.locator('.dash-recent .dash-booking')).toHaveCount(2)
  await page.screenshot({ path: '../../output/booking-history-2026-10-28/dashboard-1440.png', fullPage: true })
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  await page.screenshot({ path: '../../output/booking-history-2026-10-28/dashboard-390.png', fullPage: true })
})

test('booking staff overview retains its tasks with a compact status line', async ({ page }) => {
  await page.route('**/api/v1/admin/overview/', route => route.fulfill({ json: { ...emptyOverview('MANAGER'),
    pending_bookings: 3, urgent_requests: 1, pending_inductions: 2,
    today_count: 1, today: [approvedBooking({ check_in_open: false })],
  } }))
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/admin/today') // 2026-11-07: a Manager lands on the Lab overview
  await page.setViewportSize({ width: 1440, height: 1000 })
  await expect(page.getByRole('link', { name: /Booking requests to decide/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: /Bookings today/ })).toBeVisible()
  expect((await page.locator('.today-brief').boundingBox())!.height).toBeLessThan(60)
  await page.screenshot({ path: '../../output/booking-history-2026-10-28/today-1440.png', fullPage: true })
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
  await page.screenshot({ path: '../../output/booking-history-2026-10-28/today-390.png', fullPage: true })
})

const recurringRoom = { id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
  required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00:00', closing_time: '20:00:00',
  timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null, category: null }

function seriesAvailability(overrides: Record<string, unknown> = {}) {
  return { resource_id: recurringRoom.id, date: '2030-01-01', timezone: 'Australia/Sydney', duration_minutes: 30,
    slots: [], can_request: true, qualification_status: 'VERIFIED', earliest_date: '2030-01-08', latest_date: '2030-01-29',
    min_advance_days: 7, max_advance_days: 28, ...overrides }
}

test('staff book a weekly series and skip the dates with a problem', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
  const room = recurringRoom
  const occurrence = (date: string, available = true, reason: string | null = null) => ({
    date, start: `${date}T22:00:00Z`, end: `${date}T23:00:00Z`, available, reason_code: reason, message: reason ? 'Problem' : null })
  const created: Record<string, unknown>[] = []
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [room] } })
    if (path === 'resources/room-1/availability/') return route.fulfill({ json: seriesAvailability() })
    if (path === 'bookings/series/preview/') {
      return route.fulfill({ json: { resource_id: 'room-1', booking_for: { id: 'test-admin', zid: 'z9000001', display_name: 'Test Admin', role: 'ADMIN' },
        weekdays: request.postDataJSON().weekdays, available_count: 2,
        occurrences: [occurrence('2030-01-14'), occurrence('2030-01-21', false, 'BOOKING_CONFLICT'), occurrence('2030-01-28')] } })
    }
    if (path === 'bookings/series/' && request.method() === 'POST') {
      created.push(request.postDataJSON())
      return route.fulfill({ status: 201, json: { id: 's1', bookings: [approvedBooking({ id: 'a' }), approvedBooking({ id: 'b' })] } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.goto('/#/resources')
  await page.getByRole('button', { name: 'Repeat weekly', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Repeat weekly: Lab Room 1' })).toBeVisible()
  await expect(page.getByLabel('First date')).toHaveValue('2030-01-08')
  await expect(page.getByLabel('Last date')).toHaveValue('2030-01-29')
  await expect(page.getByLabel('Last date')).toHaveAttribute('max', '2030-01-29')
  await page.getByLabel('First date').fill('2030-01-14')
  await page.getByLabel('Last date').fill('2030-01-28')
  await page.getByRole('checkbox', { name: 'Tue', exact: true }).uncheck()
  await page.getByRole('checkbox', { name: 'Mon', exact: true }).check()
  await page.getByRole('button', { name: 'Check dates', exact: true }).click()
  const table = page.getByRole('table', { name: 'Dates in this series' })
  await expect(table.locator('tbody tr')).toHaveCount(3)
  await expect(table).toContainText('Skipped: Already booked or held')
  await page.getByPlaceholder('e.g. Weekly COMP lab session').fill('Weekly lab')
  await page.getByRole('button', { name: 'Book 2 date(s)', exact: true }).click()
  await page.getByRole('dialog', { name: 'Book 2 date(s)?' }).getByRole('button', { name: 'Book series', exact: true }).click()
  await expect(page.getByText('2 date(s) booked for Test Admin.')).toBeVisible()
  expect(created).toHaveLength(1)
  expect(created[0].skip_dates).toEqual(['2030-01-21'])
  expect(created[0].purpose).toBe('Weekly lab')
})

for (const role of ['ADMIN', 'MANAGER'] as const) {
  test(`${role} weekly series follows configured dates for self and on behalf`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
    const previews: Record<string, unknown>[] = []
    const recipients: (string | null)[] = []
    await page.route('**/api/v1/**', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname.replace('/api/v1/', '')
      if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [recurringRoom] } })
      if (path === 'resources/room-1/availability/') {
        recipients.push(url.searchParams.get('for_zid'))
        if (role === 'MANAGER') return route.fulfill({ json: seriesAvailability({
          manager_override: true, earliest_date: '2030-01-01', latest_date: null,
          normal_booking_window: { earliest_date: '2030-01-08', latest_date: '2030-01-15', max_advance_days: 14 },
        }) })
        return route.fulfill({ json: seriesAvailability({ latest_date: '2030-01-15', max_advance_days: 14 }) })
      }
      if (path === 'people/lookup/') return route.fulfill({ json: users.STUDENT })
      if (path === 'bookings/series/preview/') {
        previews.push(request.postDataJSON())
        return route.fulfill({ json: { resource_id: recurringRoom.id, booking_for: users.STUDENT,
          weekdays: [2], occurrences: [], available_count: 0 } })
      }
      return route.fallback()
    })
    await page.goto('/#/login')
    await signIn(page, role)
    await page.goto('/#/resources')
    await page.getByRole('button', { name: 'Repeat weekly', exact: true }).click()
    const first = page.getByLabel('First date')
    const last = page.getByLabel('Last date')
    const check = page.getByRole('button', { name: 'Check dates', exact: true })
    await expect(first).toHaveValue('2030-01-08')
    await expect(first).toHaveAttribute('min', '2030-01-08')
    await expect(first).toHaveAttribute('max', '2030-01-15')
    await expect(last).toHaveValue('2030-01-15')
    await expect(page.getByText('Every date must be from 8 Jan 2030 to 15 Jan 2030 (at most 14 days ahead).')).toBeVisible()
    await last.fill('2030-01-16')
    await expect(check).toBeDisabled()
    await expect(page.getByRole('alert')).toContainText('Every date in the series must fit the booking window')
    await last.fill('2030-01-15')
    await first.fill('2030-01-07')
    await expect(check).toBeDisabled()
    await first.fill('2030-01-08')
    await expect(check).toBeEnabled()
    await page.getByRole('radio', { name: 'Someone else', exact: true }).check()
    await expect(check).toBeDisabled()
    await page.getByLabel('zID of the person', { exact: true }).fill(users.STUDENT.zid)
    await page.getByRole('button', { name: 'Check', exact: true }).click()
    await expect(last).toHaveAttribute('max', '2030-01-15')
    await expect(check).toBeEnabled()
    await check.click()
    await expect(page.getByRole('table', { name: 'Dates in this series' })).toBeVisible()
    expect(recipients).toContain(null)
    expect(recipients.at(-1)).toBe(users.STUDENT.zid)
    expect(previews).toEqual([expect.objectContaining({ first_date: '2030-01-08', last_date: '2030-01-15', on_behalf_of_zid: users.STUDENT.zid })])
  })
}

test('weekly series test override has no upper date limit but on-behalf bookings restore it', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-01T00:00:00Z'))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/v1/', '')
    if (path === 'auth/me/') return route.fulfill({ json: { ...users.ADMIN, test_account: true, bypass_booking_rules: true } })
    if (path === 'resources/') return route.fulfill({ json: { count: 1, results: [recurringRoom] } })
    if (path === 'people/lookup/') return route.fulfill({ json: users.STUDENT })
    if (path === 'resources/room-1/availability/') return route.fulfill({ json: url.searchParams.has('for_zid')
      ? seriesAvailability()
      : seriesAvailability({ test_bypass: true, earliest_date: '2030-01-01', latest_date: null, min_advance_days: 0, max_advance_days: 0 }) })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.goto('/#/resources')
  await page.getByRole('button', { name: 'Repeat weekly', exact: true }).click()
  const first = page.getByLabel('First date')
  const last = page.getByLabel('Last date')
  const check = page.getByRole('button', { name: 'Check dates', exact: true })
  await expect(first).toHaveValue('2030-01-01')
  await expect(first).not.toHaveAttribute('max')
  await expect(last).not.toHaveAttribute('max')
  await last.fill('2030-03-01')
  await expect(check).toBeEnabled()
  await page.getByRole('radio', { name: 'Someone else', exact: true }).check()
  await expect(check).toBeDisabled()
  await page.getByLabel('zID of the person', { exact: true }).fill(users.STUDENT.zid)
  await page.getByRole('button', { name: 'Check', exact: true }).click()
  await expect(first).toHaveValue('2030-01-08')
  await expect(last).toHaveValue('2030-01-29')
  await expect(first).toHaveAttribute('max', '2030-01-29')
  await expect(last).toHaveAttribute('max', '2030-01-29')
  await expect(check).toBeEnabled()
})

// Sprint 3: Managers add and edit rooms and equipment.
test('a Manager adds equipment and sees bookings that no longer fit an edit', async ({ page }) => {
  const room = { id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
    required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00:00', closing_time: '20:00:00',
    timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null, category: null }
  const resources: Record<string, unknown>[] = [room]
  const sent: { method: string; path: string; body: Record<string, unknown> }[] = []
  let internalAttempts = 0
  let releaseInternal!: () => void
  const internalReady = new Promise<void>((resolve) => { releaseInternal = resolve })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'qualification-requirements/') {
      return route.fulfill({ json: { count: 1, results: [{ id: 'req-1', name: 'General laboratory induction', description: '', prerequisite_ids: [] }] } })
    }
    if (path === 'admin/resources/' && request.method() === 'GET') return route.fulfill({ json: { count: resources.length, results: resources } })
    if (path === 'admin/resources/' && request.method() === 'POST') {
      const body = request.postDataJSON()
      sent.push({ method: 'POST', path, body })
      const created = { ...room, ...body, id: 'eq-9', opening_time: `${body.opening_time}:00`, closing_time: `${body.closing_time}:00` }
      resources.push(created)
      return route.fulfill({ status: 201, json: created })
    }
    if (path === 'admin/resources/eq-9/internal/' && request.method() === 'PATCH') {
      internalAttempts++
      if (internalAttempts === 1) return route.fulfill({ status: 503, json: { detail: 'Try again.' } })
      expect(request.postDataJSON()).toEqual({ asset_number: 'A-900' })
      return route.fulfill({ json: { resource_id: 'eq-9', asset_number: 'A-900' } })
    }
    if (path === 'admin/resources/room-1/internal/' && request.method() === 'GET') {
      await internalReady
      return route.fulfill({ json: { resource_id: 'room-1', owner: 'Lab team', asset_number: '', provided_by: '', specifications: '', updated_at: null, updated_by: null } })
    }
    if (path === 'admin/resources/room-1/' && request.method() === 'PATCH') {
      const body = request.postDataJSON()
      sent.push({ method: 'PATCH', path, body })
      return route.fulfill({ json: { resource: { ...room, closing_time: '17:00:00' }, bookings_outside_rules: [{
        ...approvedBooking({ id: 'late' }), student: { id: 's', zid: 'z1000001', display_name: 'Test Student', university_email: 'z1000001@ad.unsw.edu.au' },
        problem: 'OUTSIDE_OPENING_HOURS' }] } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Resources', exact: true }).click()
  await expect(page.getByRole('table', { name: 'Resources' })).toContainText('Lab Room 1')

  await page.getByRole('button', { name: '+ Add equipment', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add equipment' })
  await dialog.getByLabel('Name').fill('Spectrometer 900')
  await dialog.getByLabel('Location').fill('Lab Room 1, bench 4')
  await dialog.getByLabel('Kept in room').selectOption('room-1')
  await dialog.getByLabel('Equipment type').fill('Optics')
  await dialog.getByLabel('UNSW asset number').fill('A-900')
  await dialog.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(dialog.getByRole('alert')).toBeVisible()
  await dialog.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByRole('table', { name: 'Resources' })).toContainText('Spectrometer 900')
  expect(internalAttempts).toBe(2)
  expect(sent.filter(({ method }) => method === 'POST')).toHaveLength(1)
  expect(sent[0].body).toMatchObject({ kind: 'EQUIPMENT', name: 'Spectrometer 900', room_id: 'room-1', category: 'Optics',
    required_qualification_id: 'req-1', slot_minutes: 30, opening_time: '08:00', closing_time: '20:00' })

  await page.getByRole('tab', { name: /Rooms/ }).click()
  await page.getByRole('button', { name: 'Edit Lab Room 1', exact: true }).click()
  const edit = page.getByRole('dialog', { name: 'Edit Lab Room 1' })
  await expect(edit.getByLabel('Owner')).toBeDisabled()
  releaseInternal()
  await expect(edit.getByLabel('Owner')).toHaveValue('Lab team')
  await edit.getByLabel('Closes').fill('17:00')
  await edit.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByRole('status', { name: 'Bookings outside the new rules' })).toContainText('outside the new opening hours')
  expect(sent[1]).toEqual({ method: 'PATCH', path: 'admin/resources/room-1/', body: { closing_time: '17:00' } })
})

test('Admins do not see the Resources page', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Resources', exact: true })).toHaveCount(0)
  await page.goto('/#/manager/resources')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
})

// Sprint 3: usage statistics tab of Booking Records (Managers only since 2026-11-07).
test('a Manager reads the usage statistics on Booking Records; an Admin has no such tab', async ({ page }) => {
  const figures = { approved: 3, booked_hours: 4.5, open_hours: 84, utilisation: 0.054, checked_in: 1, no_show: 1, excused: 0,
    not_tracked: 0, attendance_rate: 0.5, cancelled: 1, rejected: 0 }
  const asked: string[] = []
  await page.route('**/api/v1/admin/reports/usage/**', async (route) => {
    asked.push(new URL(route.request().url()).search)
    return route.fulfill({ json: { first_date: '2030-01-01', last_date: '2030-01-28', days: 28, totals: figures,
      results: [{ resource_id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', category: null, room_name: null, active: true, ...figures }] } })
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Booking records', exact: true }).click()
  await expect(page.getByText('Admins see bookings from the last 7 days')).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Usage statistics', exact: true })).toHaveCount(0)
  await signOut(page)
  await signIn(page, 'MANAGER')
  await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Booking records', exact: true }).click()
  await page.getByRole('tab', { name: 'Usage statistics', exact: true }).click()
  await expect(page).toHaveURL(/#\/admin\/records\?tab=usage$/)
  const table = page.getByRole('table', { name: 'Usage by resource' })
  await expect(table).toContainText('Lab Room 1')
  await expect(table).toContainText('50%')
  await expect(page.getByLabel('Totals')).toContainText('4.5 hours booked')
  expect(asked[0]).toMatch(/first_date=\d{4}-\d{2}-\d{2}&last_date=\d{4}-\d{2}-\d{2}/)
})

test('the old Usage Report address opens the usage statistics tab', async ({ page }) => {
  await page.route('**/api/v1/admin/reports/usage/**', (route) => route.fulfill({ json: { first_date: '2030-01-01', last_date: '2030-01-28', days: 28,
    totals: { approved: 0, booked_hours: 0, open_hours: 0, utilisation: null, checked_in: 0, no_show: 0, excused: 0, not_tracked: 0, attendance_rate: null, cancelled: 0, rejected: 0 },
    results: [] } }))
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/manager/usage')
  await expect(page).toHaveURL(/#\/admin\/records\?tab=usage$/)
  await expect(page.getByRole('tab', { name: 'Usage statistics', exact: true })).toHaveAttribute('aria-selected', 'true')
})

// Sprint 3: Booking Records tab: filters (including name/zID search) and a CSV of the same list.
test('staff search booking records and export the same list as CSV', async ({ page }) => {
  const asked: URLSearchParams[] = []
  const exported: URLSearchParams[] = []
  const record = approvedBooking({ id: 'r1', resource_name: 'Lab Room 1', attendance: 'NO_SHOW', check_in_open: false,
    student: { id: 'test-student', zid: 'z1000001', display_name: 'Test Student', university_email: 'student@example.test' },
    on_behalf: true, created_by_user: { id: 'test-admin', zid: 'z9000001', display_name: 'Test Admin', role: 'ADMIN' } })
  await page.route('**/api/v1/admin/bookings/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/export/')) {
      exported.push(url.searchParams)
      return route.fulfill({ status: 200, headers: { 'Content-Type': 'text/csv; charset=utf-8' }, body: 'Booking ID\nr1\n' })
    }
    asked.push(url.searchParams)
    const q = url.searchParams.get('q')
    return route.fulfill({ json: !q || q === 'z1000001' ? { count: 1, results: [record] } : { count: 0, results: [] } })
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/admin/records')
  await expect(page.getByRole('heading', { name: 'Booking records', exact: true })).toBeVisible()
  const table = page.getByRole('table', { name: 'Bookings' })
  await expect(table).toContainText('Test Student')
  await expect(table).toContainText('Test Admin (z9000001)')
  await expect(table).toContainText('Missed (no check-in)')
  // Only the records list sends since/until (the Manager home page also lists approved bookings).
  const records = asked.filter((params) => params.has('since'))
  expect(records[0].get('status')).toBe('ALL')
  expect(records[0].get('since')).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00\+1[01]:00$/)
  await page.getByLabel('Name or zID').fill('nobody')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByText('No bookings match these filters')).toBeVisible()
  await page.getByLabel('Name or zID').fill('z1000001')
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(table).toContainText('Test Student')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV', exact: true }).click()
  expect((await download).suggestedFilename()).toMatch(/^smartlab-bookings-.*\.csv$/)
  expect(exported[0].get('q')).toBe('z1000001')
  expect(exported[0].get('since')).toBe(records[0].get('since'))
})

test('students do not see Booking Records', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Booking records', exact: true })).toHaveCount(0)
  await page.goto('/#/admin/records')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
})

// Sprint 3: a weekly series is one card on My Bookings; dates open underneath and are cancelled one at a time.
test('my bookings shows a weekly series as one card', async ({ page }) => {
  const cancelled: string[] = []
  const series = (id: string, start: string, end: string, extra: Record<string, unknown> = {}) =>
    approvedBooking({ id, start, end, series_id: 'S1', check_in_open: false, on_behalf: true,
      created_by_user: { id: 'test-admin', zid: 'z9000001', display_name: 'Test Admin', role: 'ADMIN' }, ...extra })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'bookings/' && request.method() === 'GET') {
      return route.fulfill({ json: { count: 3, results: [
        series('d2', '2099-01-14T22:00:00Z', '2099-01-14T23:00:00Z'), // Thu 15 Jan 2099, 09:00 Sydney
        series('d1', '2099-01-12T22:00:00Z', '2099-01-12T23:00:00Z', { check_in_open: true }), // Tue 13 Jan 2099
        series('d3', '2099-01-19T22:00:00Z', '2099-01-19T23:00:00Z'), // Tue 20 Jan 2099
      ] } })
    }
    if (path === 'bookings/d3/cancel/' && request.method() === 'POST') {
      cancelled.push('d3')
      return route.fulfill({ json: series('d3', '2099-01-19T22:00:00Z', '2099-01-19T23:00:00Z', { status: 'CANCELLED' }) })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/bookings')
  const card = page.locator('.bk-series-card')
  await expect(card).toHaveCount(1)
  await expect(card).toContainText('Weekly series')
  await expect(card).toContainText('Every Tue, Thu · 9:00 am – 10:00 am')
  await expect(card).toContainText('3 of 3 dates left')
  await expect(card).toContainText('Booked for you by Test Admin (z9000001)')
  await expect(card.getByRole('button', { name: "I'm here", exact: true })).toBeVisible()
  await expect(card.getByRole('button', { name: 'Cancel the rest', exact: true })).toHaveCount(0) // staff only
  await card.getByRole('button', { name: 'Show dates (3)', exact: true }).click()
  const dates = card.getByRole('list', { name: 'Series dates' })
  await expect(dates.getByRole('listitem')).toHaveCount(3)
  await dates.getByRole('listitem').nth(2).getByRole('button', { name: 'Cancel this date', exact: true }).click()
  await page.getByRole('dialog', { name: 'Cancel this booking?' }).getByRole('button', { name: 'Cancel booking', exact: true }).click()
  expect(cancelled).toEqual(['d3'])
})

// Sprint 3: the inductions are one line at the top of Book a resource.
test('book a resource keeps missing inductions open with an upload link', async ({ page }) => {
  const room = { id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
    required_qualification_id: 'req-2', slot_minutes: 30, max_booking_minutes: 240, opening_time: '08:00:00', closing_time: '20:00:00',
    timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null, category: null }
  const general = { ...room, id: 'room-2', name: 'Lab Room 2', required_qualification_id: 'req-1' }
  const verified = (id: string, requirement: string, title: string) => ({ id, requirement_id: requirement, effective_status: 'VERIFIED',
    status: 'VERIFIED', submitted_at: '2030-01-01T00:00:00Z', title, valid_until: '2099-01-01T00:00:00Z' })
  const quals = [verified('q1', 'req-1', 'General')]
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'resources/' && request.method() === 'GET') return route.fulfill({ json: { count: 2, results: [room, general] } })
    if (path === 'qualification-requirements/') {
      return route.fulfill({ json: { count: 2, results: [
        { id: 'req-1', name: 'General', description: 'Safety basics', prerequisite_ids: [] },
        { id: 'req-2', name: 'Advanced', description: 'Equipment training', prerequisite_ids: [] },
      ] } })
    }
    if (path === 'qualifications/') return route.fulfill({ json: { count: quals.length, results: quals } })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/resources')
  // Sprint 3 (review R2): one induction is missing, so the details are open and the count is not shown as done.
  const strip = page.getByRole('group', { name: 'Your inductions' })
  await expect(strip).toBeVisible()
  await expect(page.locator('.bk-access-summary > summary > span')).toHaveText('1/2 verified')
  await expect(page.locator('.bk-access-summary > summary > span')).toHaveClass('is-warn')
  await expect(strip).toContainText('General verified')
  await expect(strip).toContainText('Advanced not submitted')
  await expect(strip).toHaveClass(/is-warn/)
  await strip.getByRole('link', { name: 'Upload', exact: true }).click()
  await expect(page).toHaveURL(/#\/induction\?requirement=req-2$/)
  // Wait until the induction page has rendered: going back before then can collapse both navigations into one.
  await expect(page.getByRole('heading', { name: 'Induction & training', exact: true })).toBeVisible()

  // With every induction verified the details fold away behind the summary.
  quals.push(verified('q2', 'req-2', 'Advanced'))
  await page.goto('/#/resources')
  await expect(page.locator('.bk-access-summary > summary > span')).toHaveText('2/2 verified')
  await expect(strip).toBeHidden()
  await page.getByText('Training requirements', { exact: false }).click()
  await expect(strip).toHaveClass(/is-ok/)
})

// Sprint 3: staff change their own password on the Account page.
test('staff change their password on the Account page; students do not see it', async ({ page }) => {
  const sent: unknown[] = []
  await page.route('**/api/v1/auth/change-password/', async (route) => {
    sent.push(route.request().postDataJSON())
    return route.fulfill({ json: { changed: true } })
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await page.goto('/#/account')
  const form = page.getByRole('form', { name: 'Change password' })
  await form.getByLabel('Current password').fill('123')
  await form.getByLabel('New password', { exact: true }).fill('a-new-password')
  await form.getByLabel('New password again').fill('a-new-passwor')
  await expect(form.getByRole('alert')).toContainText('The two new passwords differ.')
  await form.getByLabel('New password again').fill('a-new-password')
  await form.getByRole('button', { name: 'Change password', exact: true }).click()
  await expect(page.getByText('Use the new password next time you sign in.')).toBeVisible()
  expect(sent).toEqual([{ current_password: '123', new_password: 'a-new-password' }])
})

test('students have no password form', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/account')
  await expect(page.getByRole('heading', { name: 'Account details' })).toBeVisible()
  await expect(page.getByRole('form', { name: 'Change password' })).toHaveCount(0)
})

// Sprint 3 (1.16.0): fixes from the user review.
const reviewRoom = { id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
  required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00:00', closing_time: '20:00:00',
  timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null, category: null,
  capacity: 12, details: [{ label: 'Floor', value: 'Level 3' }] }
const reviewSlot = (start: string, end: string, extra: Record<string, unknown> = {}) =>
  ({ start, end, available: true, reason_code: null, hold_until: null, held_by_me: false, requested_by_me: false, ...extra })

test('a student asks to move a booking; a taken time can only join the waitlist', async ({ page }) => {
  const sent: unknown[] = []
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'bookings/' && request.method() === 'GET') return route.fulfill({ json: { count: 1, results: [approvedBooking({ check_in_open: false })] } })
    if (path === 'resources/' && request.method() === 'GET') return route.fulfill({ json: { count: 1, results: [reviewRoom] } })
    if (path === 'resources/room-1/availability/') {
      return route.fulfill({ json: {
        resource_id: 'room-1', date: '2030-01-10', timezone: 'Australia/Sydney', duration_minutes: 30, can_request: true, qualification_status: 'VERIFIED',
        earliest_date: '2030-01-03', latest_date: '2030-02-02', min_advance_days: 7, max_advance_days: 30, resource_status: 'AVAILABLE', status_reason: null,
        slots: [reviewSlot('2030-01-09T21:00:00Z', '2030-01-09T21:30:00Z'),
          reviewSlot('2030-01-09T21:30:00Z', '2030-01-09T22:00:00Z', { available: false, reason_code: 'BOOKED' }),
          reviewSlot('2030-01-09T22:00:00Z', '2030-01-09T22:30:00Z')],
      } })
    }
    if (path === 'bookings/bk-1/change/' && request.method() === 'POST') {
      sent.push(request.postDataJSON())
      return route.fulfill({ status: 201, json: approvedBooking({ id: 'bk-2', status: 'WAITLISTED', start: '2030-01-09T21:30:00Z', end: '2030-01-09T22:00:00Z',
        replaces_id: 'bk-1', replaces_booking: { id: 'bk-1', start: '2030-01-10T00:00:00Z', end: '2030-01-10T01:00:00Z', status: 'APPROVED' } }) })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/bookings')
  await page.getByRole('button', { name: 'Change time', exact: true }).click()
  await expect(page.getByText(/stays until the new time is approved/).first()).toBeVisible()
  await page.getByLabel('Length').selectOption({ label: '0.5 h' })
  await page.getByLabel('Start time').selectOption({ label: '8:30 am (waitlist)' })
  await expect(page.getByText(/already booked by someone else, so your change can only join the waitlist/)).toBeVisible()
  await page.getByRole('button', { name: 'Join the waitlist for this time', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Join the waitlist for this time?' })).toBeVisible()
  await page.getByRole('button', { name: 'Join waitlist', exact: true }).click()
  await expect(page.getByText('Change on the waitlist')).toBeVisible()
  expect(sent).toEqual([{ start: '2030-01-09T21:30:00Z', end: '2030-01-09T22:00:00Z' }])
})

// Sprint 3 (review R1): a toast is hidden under a modal dialog's backdrop, so a failed move is also shown inside the dialog.
test('Room Management shows a failed reschedule inside the dialog', async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'admin/bookings/' && request.method() === 'GET') {
      return route.fulfill({ json: { count: 1, results: [approvedBooking({ student: { id: 'test-student', zid: 'z1000001', display_name: 'Test Student' } })] } })
    }
    if (path === 'resources/' && request.method() === 'GET') return route.fulfill({ json: { count: 1, results: [reviewRoom] } })
    if (path === 'resources/room-1/availability/') {
      return route.fulfill({ json: {
        resource_id: 'room-1', date: '2030-01-10', timezone: 'Australia/Sydney', duration_minutes: 30, can_request: true, qualification_status: 'VERIFIED',
        earliest_date: '2030-01-03', latest_date: '2030-02-02', min_advance_days: 7, max_advance_days: 30, resource_status: 'AVAILABLE', status_reason: null,
        slots: [reviewSlot('2030-01-09T21:00:00Z', '2030-01-09T21:30:00Z'), reviewSlot('2030-01-09T21:30:00Z', '2030-01-09T22:00:00Z')],
      } })
    }
    if (path === 'bookings/bk-1/reschedule/' && request.method() === 'POST') {
      return route.fulfill({ status: 409, json: { error: { code: 'BOOKING_CONFLICT', message: 'That time was just booked by someone else.' } } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/manager/bookings')
  await page.getByRole('button', { name: 'Reschedule', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Reschedule booking', exact: true })
  await dialog.getByLabel('Start time').selectOption({ label: '8:00 am' })
  await dialog.getByRole('button', { name: 'Confirm new time', exact: true }).click()
  await page.getByRole('button', { name: 'Move booking', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Booking not moved: That time is already booked.')
})

// 2026-10-29 (Loy): the weekly-limit error only appeared as a toast behind the booking dialog; the dialog showed nothing,
// because reloading the day after the failure cleared the error together with the selection.
test('a refused booking request is explained inside the booking dialog', async ({ page }) => {
  let availabilityLoads = 0
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'resources/' && request.method() === 'GET') return route.fulfill({ json: { count: 1, results: [reviewRoom] } })
    if (path === 'resources/room-1/availability/') {
      availabilityLoads += 1
      return route.fulfill({ json: {
        resource_id: 'room-1', date: '2030-01-10', timezone: 'Australia/Sydney', duration_minutes: 30, can_request: true, qualification_status: 'VERIFIED',
        earliest_date: '2030-01-03', latest_date: '2030-02-02', min_advance_days: 7, max_advance_days: 30, resource_status: 'AVAILABLE', status_reason: null,
        slots: [reviewSlot('2030-01-09T21:00:00Z', '2030-01-09T21:30:00Z'), reviewSlot('2030-01-09T21:30:00Z', '2030-01-09T22:00:00Z'),
          reviewSlot('2030-01-09T22:00:00Z', '2030-01-09T22:30:00Z')],
      } })
    }
    if (path === 'bookings/' && request.method() === 'POST') {
      return route.fulfill({ status: 409, json: { error: { code: 'WEEKLY_LIMIT_REACHED',
        message: 'A person may book up to 12 h in one week (Monday to Sunday).',
        details: { limit_slots: 24, used_slots: 24, requested_slots: 1, remaining_slots: 0, slot_minutes: 30, week_start: '2030-01-07' } } } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/resources')
  await page.getByRole('button', { name: 'View availability', exact: true }).first().click()
  const dialog = page.getByRole('dialog', { name: 'Book Lab Room 1', exact: true })
  await dialog.getByLabel('Start time').selectOption({ label: '8:00 am' })
  await dialog.getByRole('textbox').last().fill('Thesis experiment')
  await dialog.getByRole('button', { name: 'Request 1 h', exact: true }).click()
  await expect.poll(() => availabilityLoads).toBeGreaterThan(1)   // the day reloads after the failure
  await expect(dialog.getByRole('alert')).toContainText('Request not submitted: A person may book up to 12 h in one week')
  await expect(dialog.getByText('Choose a time above.')).toHaveCount(0)
})

// Review D1 (2026-10-25): the day timeline appears only after the day has loaded; a vertical mouse wheel still scrolls it sideways.
test('a mouse wheel scrolls the day timeline sideways once the day has loaded', async ({ page }) => {
  const halfHours = Array.from({ length: 40 }, (_, index) => {
    const start = Date.parse('2030-01-09T21:00:00Z') + index * 30 * 60_000
    return reviewSlot(new Date(start).toISOString().replace('.000Z', 'Z'), new Date(start + 30 * 60_000).toISOString().replace('.000Z', 'Z'))
  })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'admin/bookings/' && request.method() === 'GET') {
      return route.fulfill({ json: { count: 1, results: [approvedBooking({ student: { id: 'test-student', zid: 'z1000001', display_name: 'Test Student' } })] } })
    }
    if (path === 'resources/' && request.method() === 'GET') return route.fulfill({ json: { count: 1, results: [reviewRoom] } })
    if (path === 'resources/room-1/availability/') {
      return route.fulfill({ json: {
        resource_id: 'room-1', date: '2030-01-10', timezone: 'Australia/Sydney', duration_minutes: 30, can_request: true, qualification_status: 'VERIFIED',
        earliest_date: '2030-01-03', latest_date: '2030-02-02', min_advance_days: 7, max_advance_days: 30, resource_status: 'AVAILABLE', status_reason: null,
        slots: halfHours,
      } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/manager/bookings')
  await page.getByRole('button', { name: 'Reschedule', exact: true }).click()
  const timeline = page.getByRole('dialog', { name: 'Reschedule booking', exact: true }).locator('.ui-tl-scroll')
  await expect(timeline).toBeVisible()
  expect(await timeline.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
  await timeline.hover()
  await page.mouse.wheel(0, 300)
  await expect.poll(() => timeline.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0)
})

// Sprint 3 (UI review #1): on a 390 px phone, wide tables and tab rows scroll inside themselves; the page never gets wider than the screen.
test('phone width: tables and tab rows never make a page wider than the screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (request.method() !== 'GET') return route.fallback()
    if (path === 'resources/' || path === 'admin/resources/') return route.fulfill({ json: { count: 1, results: [reviewRoom] } })
    if (path === 'admin/bookings/') {
      return route.fulfill({ json: { count: 1, results: [approvedBooking({ student: { id: 'test-student', zid: 'z1000001', display_name: 'Test Student' } })] } })
    }
    if (path === 'qualification-requirements/') {
      return route.fulfill({ json: { count: 1, results: [{ id: 'req-1', name: 'General laboratory induction', description: 'Safety basics', prerequisite_ids: [] }] } })
    }
    return route.fallback()
  })
  const widerThanScreen = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)

  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/bookings')
  const cancelled = page.getByRole('tab', { name: /^Cancelled/ })
  await expect(cancelled).toBeAttached()
  expect(await widerThanScreen(), '/bookings').toBe(0)
  await cancelled.click()
  await expect(cancelled).toHaveAttribute('aria-selected', 'true')
  await signOut(page)

  await signIn(page, 'MANAGER')
  for (const path of ['/manager/bookings', '/manager/resources', '/manager/users', '/manager/setup']) {
    await page.goto(`/#${path}`)
    await expect(page.locator('.ui-table-wrap th').first()).toBeVisible()
    expect(await widerThanScreen(), path).toBe(0)
  }
})

// 2026-11-07 (client, Week 8): the three roles look different; a Manager starts on the Lab overview.
test('a Manager starts on the Lab overview, sees the role badge and looks up a zID', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await expect(page.getByText('Admin view', { exact: true })).toBeVisible()
  await signOut(page)
  await signIn(page, 'MANAGER')
  await expect(page).toHaveURL(/#\/manager\/home$/)
  await expect(page.getByText('Manager view', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Only a Manager decides', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Urgent requests/ })).toBeVisible()
  await page.getByLabel('zID to look up').fill('z12')
  await page.getByRole('button', { name: 'Look up', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('z followed by 7 digits')
  await page.getByLabel('zID to look up').fill('Z1000001')
  await page.getByRole('button', { name: 'Look up', exact: true }).click()
  await expect(page).toHaveURL(/#\/admin\/records\?q=z1000001$/)
  await expect(page.getByLabel('Name or zID')).toHaveValue('z1000001')
})

test('staff start on Today, whose cards open the pages that handle them', async ({ page }) => {
  await page.route('**/api/v1/admin/overview/', (route) => route.fulfill({ json: {
    role: 'ADMIN', pending_inductions: 2, pending_bookings: 3, urgent_requests: 1, waitlisted: 0, changes_waiting: 1,
    due_soon: [approvedBooking({ status: 'PENDING_APPROVAL', review_due_at: '2030-01-01T02:00:00Z' })], due_soon_hours: 6,
    out_of_service: [{ resource: { ...reviewRoom, status: 'MAINTENANCE', status_reason: 'Water leak' }, affected_bookings: 2 }],
    today: [], today_count: 0, missed_today: 0, can_decide_urgent: false } }))
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await expect(page).toHaveURL(/#\/admin\/today$/)
  await expect(page.getByRole('heading', { name: 'Today', exact: true })).toBeVisible()
  // 2026-11-07 (client, Week 8): an Admin's Today has review work only; what a Manager decides is on the Manager home.
  await expect(page.getByRole('link', { name: /Urgent requests/ })).toHaveCount(0)
  await expect(page.getByText('Water leak')).toBeVisible()
  await expect(page.getByText('2 future bookings')).toBeVisible()
  // Sprint 3 (2026-10-28 feedback L2, L5): urgent has its own red line; the check only shows when nothing waits.
  await expect(page.getByRole('link', { name: /Booking requests to decide/ })).toHaveCSS('border-top-color', 'rgb(173, 63, 57)')
  await expect(page.locator('.today-brief-mark')).toHaveCount(0)
  await page.getByRole('link', { name: /Induction evidence to review/ }).click()
  await expect(page).toHaveURL(/#\/admin\/qualifications$/)
})

test('Today keeps a lone card and a lone panel in proportion', async ({ page }) => {
  // Sprint 3 (2026-10-28 feedback L2): one card stays a third wide; a panel without its neighbour spans the row.
  await page.route('**/api/v1/admin/overview/', (route) => route.fulfill({ json: {
    role: 'ADMIN', pending_inductions: 1, pending_bookings: 0, urgent_requests: 0, waitlisted: 0, changes_waiting: 0,
    due_soon: [], due_soon_hours: 6,
    out_of_service: [{ resource: { ...reviewRoom, status: 'MAINTENANCE', status_reason: 'Water leak' }, affected_bookings: 1 }],
    today: [], today_count: 0, missed_today: 0, can_decide_urgent: false } }))
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await expect(page.getByText('Water leak')).toBeVisible()
  const width = (selector: string) => page.locator(selector).first().evaluate(element => element.getBoundingClientRect().width)
  expect(await width('.today-card')).toBeLessThan(await width('.today-cards') / 2)
  expect(Math.abs(await width('.today-panel') - await width('.today-grid'))).toBeLessThan(2)
})

test('the induction page says how to get an induction and offers the lab\'s email', async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'qualification-requirements/') {
      return route.fulfill({ json: { count: 1, results: [{ id: 'req-1', name: 'General induction', description: '', prerequisite_ids: [],
        how_to_complete: 'Book the Friday safety session', accepted_evidence: 'Signed attendance sheet', reviewer: '', contact: '' }] } })
    }
    if (path === 'site/contact/') return route.fulfill({ json: { id: 'c', email: 'lab@example.edu', phone: '', hours: 'Mon-Fri', note: '' } })
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/induction')
  await expect(page.getByText('Book the Friday safety session')).toBeVisible()
  await expect(page.getByText('Signed attendance sheet')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Ask the lab about this induction' })).toHaveAttribute('href', /^mailto:lab@example\.edu\?subject=Induction%3A%20General%20induction/)
})

test('Find a free time says why nothing can be booked', async ({ page }) => {
  await page.route('**/api/v1/resources/day-overview/**', (route) => route.fulfill({ json: {
    date: '2030-01-10', duration_minutes: 60, timezone: 'Australia/Sydney', earliest_date: '2030-01-10', latest_date: '2030-02-02',
    min_advance_days: 7, max_advance_days: 30, rooms: [], categories: [], count: 0, results: [], too_long: 0, not_bookable: { NOT_SUBMITTED: 3 } } }))
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/resources')
  await page.getByRole('tab', { name: 'Find a free time', exact: true }).click()
  await page.getByLabel('Date', { exact: true }).fill('2030-01-10')
  await page.getByRole('button', { name: 'Find available resources', exact: true }).click()
  await expect(page.getByText('3 hidden: 3 induction not submitted')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Go to Induction & training' })).toBeVisible()
})

test('a Manager saves the lab\'s contact details on Lab setup', async ({ page }) => {
  const saved: unknown[] = []
  await page.route('**/api/v1/site/contact/', async (route) => {
    if (route.request().method() === 'PATCH') {
      saved.push(route.request().postDataJSON())
      return route.fulfill({ json: { id: 'c', email: 'lab@example.edu', phone: '', hours: '', note: '' } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Lab setup', exact: true }).click()
  await page.getByRole('tab', { name: 'Contact details' }).click()
  await page.getByLabel('Email').fill('lab@example.edu')
  await page.getByRole('button', { name: 'Save contact details' }).click()
  await expect(page.getByText('Contact details saved')).toBeVisible()
  expect(saved).toEqual([{ email: 'lab@example.edu', phone: '', hours: '', note: '' }])
})

// Sprint 3 (1.19.0): acceptance tests, first run against 81ef6a5 before implementing the new pages.
for (const role of ['STUDENT', 'ADMIN', 'MANAGER'] as Role[]) {
  test(`1.19 notifications: ${role} can save two independent channels and reload at 390px`, async ({ page }, testInfo) => {
    const categories = ['bookings', 'reminders', 'induction', 'account', 'resources']
    const preferences = categories.map(category => ({ category, in_app: true, email: true }))
    let available = true
    let failSave = true
    const writes: unknown[] = []
    await page.route('**/api/v1/notifications/preferences/', async route => {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON()
        if (failSave) {
          failSave = false
          return route.fulfill({ status: 503, json: { error: { code: 'TEMPORARY_FAILURE', message: 'Settings could not be saved.' } } })
        }
        writes.push(body)
        for (const [category, value] of Object.entries(body.preferences)) Object.assign(preferences.find(item => item.category === category)!, value)
      }
      await route.fulfill({ json: { results: preferences, email_available: available } })
    })
    await page.goto('/#/login')
    await signIn(page, role)
    await expect(page.getByRole('region', { name: 'Announcements', exact: true })).toHaveCount(0)
    await page.getByRole('link', { name: 'Notifications', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Notifications', exact: true })).toBeVisible()
    await expect(page.getByRole('checkbox')).toHaveCount(10)
    await page.getByRole('checkbox', { name: 'Booking updates: In the bell', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('Settings could not be saved.')
    await expect(page.getByRole('checkbox', { name: 'Booking updates: In the bell', exact: true })).toBeChecked()
    await page.getByRole('checkbox', { name: 'Booking updates: In the bell', exact: true }).click()
    await expect(page.getByRole('checkbox', { name: 'Booking updates: In the bell', exact: true })).not.toBeChecked()
    await expect(page.getByRole('checkbox', { name: 'Booking updates: By email', exact: true })).toBeChecked()
    expect(writes).toEqual([{ preferences: { bookings: { in_app: false } } }])
    await page.reload()
    await expect(page.getByRole('checkbox', { name: 'Booking updates: In the bell', exact: true })).not.toBeChecked()
    available = false
    await page.reload()
    await expect(page.getByText('Email is not switched on for this site.', { exact: true })).toBeVisible()
    await expect(page.getByRole('checkbox', { name: 'Booking updates: By email', exact: true })).toBeDisabled()
    // Review Q1 (2026-10-27): with email off the whole column shows unchecked; the saved choice returns when email is on.
    for (const category of ['Booking updates', 'Reminders', 'Induction and training', 'Missed check-ins', 'Room and equipment status']) {
      await expect(page.getByRole('checkbox', { name: `${category}: By email`, exact: true })).not.toBeChecked()
    }
    expect(writes).toHaveLength(1)
    available = true
    await page.reload()
    await expect(page.getByRole('checkbox', { name: 'Booking updates: By email', exact: true })).toBeChecked()
    await expect(page.getByRole('checkbox', { name: 'Booking updates: By email', exact: true })).toBeEnabled()
    available = false
    await page.reload()
    await expect(page.getByText('Email is not switched on for this site.', { exact: true })).toBeVisible()
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth)).toBe(true)
    expect(await page.locator('.notification-settings').evaluate(root => Array.from(root.querySelectorAll('h1,h2,p,label,span,input,button')).every(element => Number.parseFloat(getComputedStyle(element).fontSize) >= 12))).toBe(true)
    if (role === 'STUDENT') {
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo(0, 0) })
      await page.screenshot({ path: testInfo.outputPath('notifications-390.png'), fullPage: true })
    }
    await page.goto('/#/account')
    await page.getByRole('link', { name: 'Notification settings', exact: true }).click()
    await expect(page).toHaveURL(/#\/settings\/notifications$/)
  })
}

test('1.19 announcements: staff manage own notices; public boards show signatures; no 390px overflow', async ({ page }, testInfo) => {
  const base = { id: 'own', title: 'Safety update', body: 'Read the updated lab guidance.', kind: 'MANUAL', resource_id: null,
    created_by: users.ADMIN.id, author_role: 'ADMIN', author: { id: users.ADMIN.id, display_name: 'Test Admin', role: 'ADMIN' },
    created_at: '2026-10-26T00:00:00Z', updated_at: '2026-10-26T00:00:00Z', expires_at: null, expected_back: null, removed_at: null, active: true }
  const notices = [{ ...base, id: 'status', kind: 'RESOURCE_STATUS', title: 'Lab Room 1 is closed', created_by: users.MANAGER.id,
    author_role: 'MANAGER', author: { id: users.MANAGER.id, display_name: 'Test Manager', role: 'MANAGER' } }]
  let fail = true
  let failRemove = true
  await page.route('**/api/v1/announcements/**', async route => {
    const method = route.request().method()
    if (method === 'GET') return route.fulfill({ json: { count: notices.length, results: notices } })
    if (fail) { fail = false; return route.fulfill({ status: 400, json: { error: { code: 'VALIDATION_ERROR', message: 'Please check the announcement.' } } }) }
    if (method === 'POST' && route.request().url().endsWith('/announcements/')) {
      notices.push({ ...base, ...route.request().postDataJSON() })
      return route.fulfill({ status: 201, json: notices[1] })
    }
    if (method === 'PATCH') { Object.assign(notices[1], route.request().postDataJSON()); return route.fulfill({ json: notices[1] }) }
    if (failRemove) { failRemove = false; return route.fulfill({ status: 409, json: { error: { code: 'TEMPORARY_FAILURE', message: 'Please retry removing this announcement.' } } }) }
    notices.splice(1, 1)
    return route.fulfill({ json: { ...base, active: false, removed_at: '2026-10-26T01:00:00Z' } })
  })
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await expect(page.getByRole('region', { name: 'Announcements', exact: true })).toContainText('Posted by Test Manager (Manager)')
  await page.getByRole('link', { name: 'Announcements', exact: true }).click()
  await page.getByLabel('Title', { exact: true }).fill('Safety update')
  await page.getByLabel('Message', { exact: true }).fill('Read the updated lab guidance.')
  await page.getByRole('button', { name: 'Publish announcement', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Please check the announcement.')
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue('Safety update')
  await page.getByRole('button', { name: 'Publish announcement', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Edit Safety update', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Edit Lab Room 1 is closed' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Edit Safety update', exact: true }).click()
  await page.getByLabel('Title', { exact: true }).fill('Updated safety')
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Remove Updated safety', exact: true })).toBeVisible()
  // Sprint 3 (2026-10-28 feedback L3): Remove sits in the card's top-right corner, above the title.
  const removeBox = await page.getByRole('button', { name: 'Remove Updated safety', exact: true }).boundingBox()
  const cardBox = await page.locator('.announcement-history article', { hasText: 'Updated safety' }).boundingBox()
  const titleBox = await page.locator('.announcement-history article', { hasText: 'Updated safety' }).getByRole('heading').boundingBox()
  expect(removeBox!.y).toBeLessThan(titleBox!.y)
  expect(cardBox!.x + cardBox!.width - (removeBox!.x + removeBox!.width)).toBeLessThan(40)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth)).toBe(true)
  expect(await page.locator('.announcements-page').evaluate(root => Array.from(root.querySelectorAll('h1,h2,h3,p,label,span,input,textarea,button')).every(element => Number.parseFloat(getComputedStyle(element).fontSize) >= 12))).toBe(true)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  // Capture the freshly loaded mobile layout, rather than a mid-scroll desktop-to-phone resize.
  await page.reload()
  await expect(page.getByRole('button', { name: 'Remove Updated safety', exact: true })).toBeVisible()
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo(0, 0) })
  await page.screenshot({ path: testInfo.outputPath('announcements-390.png'), fullPage: true })
  await page.getByRole('button', { name: 'Remove Updated safety', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Remove announcement', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Please retry removing this announcement.')
  await page.getByRole('dialog').getByRole('button', { name: 'Remove announcement', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Edit Updated safety', exact: true })).toHaveCount(0)
  await signOut(page)
  await signIn(page, 'STUDENT')
  await expect(page.getByRole('region', { name: 'Announcements', exact: true })).toContainText('Lab Room 1 is closed')
  expect(await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth)).toBe(true)
  await expect(page.getByRole('link', { name: 'Announcements', exact: true })).toHaveCount(0)
  await page.goto('/#/admin/announcements')
  await expect(page.getByRole('heading', { name: 'Announcements', exact: true })).toHaveCount(0)
})

test('1.19 resource status keeps errors inside the form and sends the optional Sydney recovery estimate', async ({ page }) => {
  const writes: unknown[] = []
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1/', '')
    if (path === 'resources/' && route.request().method() === 'GET') return route.fulfill({ json: { count: 1, results: [reviewRoom] } })
    if (path === 'admin/resources/room-1/status/') {
      writes.push(route.request().postDataJSON())
      if (writes.length === 1) return route.fulfill({ status: 409, json: { error: { code: 'CONFLICT', message: 'Please retry this status change.' } } })
      return route.fulfill({ json: { resource: { ...reviewRoom, status: 'MAINTENANCE' }, affected_bookings: [] } })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await page.goto('/#/manager/bookings')
  await page.getByRole('button', { name: 'Maintenance', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Put Lab Room 1 under maintenance?', exact: true })
  await dialog.getByLabel('Reason (shown to students)', { exact: true }).fill('Repairing the air conditioning')
  await dialog.getByLabel('Expected back (optional)', { exact: true }).fill('2030-01-10T12:00')
  await dialog.getByRole('button', { name: 'Start maintenance', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Please retry this status change.')
  await expect(dialog.getByLabel('Reason (shown to students)', { exact: true })).toHaveValue('Repairing the air conditioning')
  await expect(dialog.getByLabel('Expected back (optional)', { exact: true })).toHaveValue('2030-01-10T12:00')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth)).toBe(true)
  await dialog.getByRole('button', { name: 'Start maintenance', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes[1]).toEqual({ status: 'MAINTENANCE', reason: 'Repairing the air conditioning', expected_back: '2030-01-10T01:00:00.000Z' })
})

// 2026-11-07 (client, Week 8): drag the end of a booking in progress, as in a calendar; it asks a Manager.
test('a student drags the end of a booking in progress to ask a Manager for more time', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-09T23:30:00Z')) // 10:30 in Sydney
  const room = { ...recurringRoom, closing_time: '13:00:00' }
  const booking = approvedBooking({ id: 'b-ext', start: '2030-01-09T23:00:00Z', end: '2030-01-10T00:00:00Z', check_in_open: false })
  let current: Record<string, unknown> = booking
  const sent: Record<string, unknown>[] = []
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1/', '')
    if (path === 'bookings/' && request.method() === 'GET') return route.fulfill({ json: { count: 1, results: [current] } })
    if (path === 'resources/' && request.method() === 'GET') return route.fulfill({ json: { count: 1, results: [room] } })
    if (path === 'resources/room-1/availability/') {
      return route.fulfill({ json: { slots: [{ start: '2030-01-10T01:00:00Z', end: '2030-01-10T01:30:00Z', available: false,
        reason_code: 'BOOKED', hold_until: null, held_by_me: false, requested_by_me: false }] } }) // someone from 12:00
    }
    if (path === 'bookings/b-ext/extend/' && request.method() === 'POST') {
      const body = request.postDataJSON()
      sent.push(body)
      current = { ...booking, extension_end: body.end }
      return route.fulfill({ json: current })
    }
    return route.fallback()
  })
  await page.goto('/#/login')
  await signIn(page, 'STUDENT')
  await page.goto('/#/bookings')
  await page.getByRole('button', { name: 'Extend', exact: true }).click()
  const handle = page.getByRole('slider', { name: 'New end time' })
  await expect(handle).toBeEnabled()
  // Drag far to the right: it stops at 12:00, where the next booking starts.
  const track = (await page.locator('.ext-track').boundingBox())!
  await page.mouse.move(track.x + track.width * 0.4, track.y + track.height / 2)
  await page.mouse.down()
  await page.mouse.move(track.x + track.width * 0.95, track.y + track.height / 2, { steps: 5 })
  await page.mouse.up()
  await expect(handle).toHaveAttribute('aria-valuetext', /12:00/)
  await handle.press('ArrowLeft') // keyboard: back one step, to 11:30
  await expect(handle).toHaveAttribute('aria-valuetext', /11:30/)
  await page.getByRole('button', { name: 'Ask a Manager', exact: true }).click()
  await expect(page.getByText(/Waiting for a Manager/)).toBeVisible()
  expect(sent).toEqual([{ end: '2030-01-10T00:30:00.000Z' }])
})

test('a Manager approves an extension request on the Lab overview', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2030-01-09T23:30:00Z'))
  const waiting = approvedBooking({ id: 'b-ext', start: '2030-01-09T23:00:00Z', end: '2030-01-10T00:00:00Z', extension_end: '2030-01-10T01:00:00Z' })
  const decisions: Record<string, unknown>[] = []
  await page.route('**/api/v1/admin/overview/', (route) => route.fulfill({ json: {
    ...emptyOverview('MANAGER'), extension_requests: decisions.length ? [] : [waiting] } }))
  await page.route('**/api/v1/bookings/b-ext/extend/review/', (route) => {
    decisions.push(route.request().postDataJSON())
    return route.fulfill({ json: { ...waiting, end: waiting.extension_end, extension_end: null } })
  })
  await page.goto('/#/login')
  await signIn(page, 'MANAGER')
  await expect(page.getByRole('link', { name: /1\s*Extension requests/ })).toBeVisible()
  const panel = page.getByRole('heading', { name: 'Extension requests', exact: true }).locator('..')
  await expect(panel).toContainText('Test Student')
  await panel.getByRole('button', { name: 'Approve', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Extension requests', exact: true })).toHaveCount(0)
  expect(decisions).toEqual([{ decision: 'APPROVED', reason: '', expected_end: waiting.extension_end }])
})

