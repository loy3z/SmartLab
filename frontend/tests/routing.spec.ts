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
const config: AuthConfig = { mode: 'demo', demo_auth_enabled: true, demo_registration_enabled: false, sso_connected: false, token_type: 'Bearer', staff_sign_in_enabled: true }
const STAFF_PASSWORD = '123'
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
  { role: 'MANAGER', home: '/manager/bookings', heading: 'Room booking management', forbidden: '/dashboard' },
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

test('Manager returns to user management after mock login and can reopen it from navigation without changing roles', async ({ page, api }) => {
  await page.goto('/#/manager/users')
  await signIn(page, 'MANAGER')
  await expect(page).toHaveURL(/#\/manager\/users$/)
  await expect(page).toHaveTitle('User management · UNSW SmartLab')
  await expect(page.getByRole('heading', { name: 'User Management', exact: true })).toBeVisible()
  const table = page.getByRole('table')
  await expect(table.getByRole('row')).toHaveCount(accounts.length + 1)
  await expect(table.getByRole('cell', { name: users.STUDENT.zid, exact: true })).toBeVisible()
  await expect(table.getByRole('cell', { name: users.ADMIN.university_email, exact: true })).toBeVisible()
  expect(api.managerUserRequests.length).toBeGreaterThan(0)
  expect(api.managerUserRequests.every((request) => request === 'GET admin/users/')).toBe(true)
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true })
  const userManagement = navigation.getByRole('link', { name: 'User Management', exact: true })
  await expect(userManagement).toHaveAttribute('aria-current', 'page')
  await navigation.getByRole('link', { name: 'Room Management', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Room booking management', exact: true })).toBeVisible()
  api.managerUserRequests.length = 0
  await userManagement.click()
  await expect(page.getByRole('heading', { name: 'User Management', exact: true })).toBeVisible()
  await expect(table.getByRole('row')).toHaveCount(accounts.length + 1)
  await expect(userManagement).toHaveAttribute('aria-current', 'page')
  await expect(page).toHaveTitle('User management · UNSW SmartLab')
  expect(api.managerUserRequests.length).toBeGreaterThan(0)
  expect(api.managerUserRequests.every((request) => request === 'GET admin/users/')).toBe(true)
})

test('staff can book too: booking, my bookings and induction pages are in the menu (client, 17 Oct)', async ({ page }) => {
  await page.goto('/#/login')
  await signIn(page, 'ADMIN')
  await expect(page).toHaveURL('http://127.0.0.1:5174/#/admin/qualifications')
  const navigation = page.getByRole('navigation', { name: 'Main navigation', exact: true })
  for (const [menu, path, heading] of [
    ['Book a Resource', '/resources', 'Book a resource'],
    ['My Bookings', '/bookings', 'My bookings'],
  ] as const) {
    await navigation.getByRole('link', { name: menu, exact: true }).click()
    await expect(page).toHaveURL(`http://127.0.0.1:5174/#${path}`)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  }
  await expect(navigation.getByRole('link', { name: 'Induction & Training', exact: true })).toBeVisible()
  await page.goto('/#/dashboard')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
})

for (const role of ['STUDENT', 'ADMIN'] as const) {
  test(`${role} cannot enter user management or request its user data`, async ({ page, api }) => {
    await page.goto('/#/manager/users')
    await signIn(page, role)
    await expect(page).toHaveURL(role === 'STUDENT' ? /#\/dashboard$/ : /#\/admin\/qualifications$/)
    await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'User Management', exact: true })).toHaveCount(0)
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
  { label: 'Administrator', user: users.ADMIN, home: '/admin/qualifications' },
  { label: 'Manager', user: users.MANAGER, home: '/manager/bookings' },
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
  await page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Calendar Sync', exact: true }).click()
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
  await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true }).getByRole('link', { name: 'Calendar Sync', exact: true })).toHaveCount(0)
  await page.goto('/#/admin/calendar-sync')
  await expect(page.getByRole('heading', { name: 'This page is not available for your role' })).toBeVisible()
  expect(api.requests.filter((path) => path.startsWith('admin/outlook'))).toEqual([])
})

// Book a Resource -> Find a free time: filters, one row per resource, click a free time to book it.
test('find a free time shows every resource for the day and opens the booking form on the chosen time', async ({ page }) => {
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
  await expect(page.getByRole('group', { name: 'Times for Lab Room 1' })).toBeVisible()
  await expect(page.getByText('Not submitted').or(page.getByText(/induction/i)).first()).toBeVisible()
  expect(queries.some((q) => q.includes('bookable_only=true'))).toBe(true)
  await expect(page.getByRole('group', { name: 'Times for 3D Printer 001' }).getByRole('button').first()).toBeDisabled()

  await page.getByLabel('Equipment type').selectOption('Fabrication')
  await expect.poll(() => queries.some((q) => q.includes('category=Fabrication'))).toBe(true)

  await page.getByRole('group', { name: 'Times for Lab Room 1' }).getByRole('button').first().click()
  await expect(page.locator('.ui-selection')).toContainText('8:00')
  await expect(page.locator('.ui-selection')).toContainText('9:00')
})
