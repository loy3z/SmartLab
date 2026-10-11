import { expect, test as base, type Page } from '@playwright/test'
import type { AuthConfig, Dashboard, Role, User } from '../src/features/booking/types'

// Synthetic accounts exist only in these intercepted responses. No real backend is used.
const users: Record<Role, User> = {
  STUDENT: { id: 'test-student', zid: 'z1111111', display_name: 'Test Student', role: 'STUDENT', university_email: 'student@example.test', active: true },
  ADMIN: { id: 'test-admin', zid: 'z9999991', display_name: 'Test Admin', role: 'ADMIN', university_email: 'admin@example.test', active: true },
  MANAGER: { id: 'test-manager', zid: 'z9999992', display_name: 'Test Manager', role: 'MANAGER', university_email: 'manager@example.test', active: true },
}
const config: AuthConfig = { mode: 'demo', demo_auth_enabled: true, demo_registration_enabled: false, sso_connected: false, token_type: 'Bearer' }
const dashboard: Dashboard = {
  bookings: [], qualifications: [],
  counts: { WAITING_QUALIFICATION: 0, WAITLISTED: 0, PENDING_APPROVAL: 0, APPROVED: 0, REJECTED: 0, CANCELLED: 0, EXPIRED: 0 },
}
const emptyList = { count: 0, results: [] }
interface MockApi {
  me: 'ok' | 'offline' | 'expired'
  unexpected: string[]
  requests: string[]
}

const test = base.extend<{ api: MockApi }>({
  api: [async ({ page }, use) => {
    const api: MockApi = { me: 'ok', unexpected: [], requests: [] }
    await page.route('**/api/v1/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname.replace('/api/v1/', '')
      api.requests.push(path)
      const json = (data: unknown, status = 200) => route.fulfill({ status, json: data })
      if (path === 'auth/config/') return json(config)
      if (path === 'auth/demo-login/' && request.method() === 'POST') {
        const user = Object.values(users).find((item) => item.zid === request.postDataJSON().zid)
        if (user) return json({ access_token: `test-token-${user.zid}`, token_type: 'Bearer', expires_in: 3600, mode: 'demo', user })
      }
      const user = Object.values(users).find((item) => request.headers().authorization === `Bearer test-token-${item.zid}`)
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
  await page.getByLabel('University zID', { exact: true }).fill(users[role].zid)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
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
