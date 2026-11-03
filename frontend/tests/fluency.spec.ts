// Sprint 3: fluency B-card acceptance; every API response is synthetic and intercepted.
import { expect, test as base, type Page } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import type { Role } from '../src/api/types/index.ts'

const room = {
  id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
  required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00:00', closing_time: '20:00:00',
  timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null, category: null,
  capacity: 12, details: [],
}
const equipment = { ...room, id: 'equipment-1', kind: 'EQUIPMENT', name: 'Microscope 001', room_id: room.id, capacity: null, category: 'Microscopy' }
const booking = {
  id: 'booking-1', resource_id: room.id, student_id: 'student-1', created_by: null, series_id: null, status: 'APPROVED',
  start: '2030-11-03T00:00:00Z', end: '2030-11-03T01:00:00Z', created_at: '2030-10-20T00:00:00Z', revision: 1,
  purpose: 'Synthetic practical session', reason_code: null, decision_reason: null, replaces_id: null,
  student: { id: 'student-1', zid: 'z1000001', display_name: 'Test Student' }, attendance: null,
}
const pending = { ...booking, id: 'booking-2', status: 'PENDING_APPROVAL' }
const announcement = {
  id: 'notice-1', title: 'Lab closed Friday', body: 'The lab is closed for maintenance.', kind: 'MANUAL', resource_id: null,
  created_by: 'manager-1', author_role: 'MANAGER', author: { id: 'manager-1', display_name: 'Test Manager', role: 'MANAGER' },
  created_at: '2026-10-26T00:00:00Z', updated_at: '2026-10-26T00:00:00Z', expires_at: null, removed_at: null, expected_back: null, active: true,
}
interface Api {
  role: Role
  recordsGate: Promise<void> | null
  recordsFail: boolean
  roomFail: boolean
  announcementsDelay: number
  announcementsFail: boolean
  announcementsEmpty: boolean
  overviewGate: Promise<void> | null
  requests: string[]
  exports: string[]
}
const test = base.extend<{ api: Api }>({
  api: [async ({ page }, use) => {
    const api: Api = { role: 'STUDENT', recordsGate: null, recordsFail: false, roomFail: false,
      announcementsDelay: 0, announcementsFail: false, announcementsEmpty: false, overviewGate: null, requests: [], exports: [] }
    const unexpected: string[] = []
    await page.addInitScript(() => localStorage.setItem('access_token', 'synthetic-fluency-session'))
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname.replace('/api/v1/', '')
      api.requests.push(path)
      const json = (data: unknown, status = 200) => route.fulfill({ json: data, status })
      const list = (results: unknown[]) => json({ count: results.length, results })
      const failure = () => json({ error: { code: 'SYNTHETIC_FAILURE', message: 'Test connection unavailable.', details: {} } }, 500)
      if (path === 'auth/me/') return json({ id: 'synthetic-user', zid: 'z1000001', display_name: 'Test User', role: api.role, university_email: 'test@example.test', active: true })
      if (path === 'auth/config/') return json({ mode: 'demo', demo_auth_enabled: true, staff_sign_in_enabled: true })
      if (path === 'notifications/') return json({ count: 0, unread_count: 0, results: [] })
      if (path === 'resources/') return list(url.searchParams.get('kind') === 'ROOM' ? [room] : [room, equipment])
      if (path === 'qualification-requirements/') return list([{ id: 'req-1', name: 'General laboratory induction', description: 'Synthetic training', prerequisite_ids: [] }])
      if (path === 'qualifications/') return list([])
      if (path === 'announcements/') {
        if (api.announcementsDelay) await new Promise(resolveDelay => setTimeout(resolveDelay, api.announcementsDelay))
        if (api.announcementsFail) return failure()
        return list(api.announcementsEmpty ? [] : [announcement])
      }
      if (path === 'dashboard/') {
        if (api.overviewGate) await api.overviewGate
        return json({ bookings: [], qualifications: [], counts: { APPROVED: 0, PENDING_APPROVAL: 0, WAITING_QUALIFICATION: 0, WAITLISTED: 0, CANCELLED: 0, REJECTED: 0, EXPIRED: 0 },
          week_hours: { week_start: '2030-01-07', used_hours: 0, limit_hours: 12 } })
      }
      if (path === 'admin/overview/') {
        if (api.overviewGate) await api.overviewGate
        return json({ role: api.role, pending_inductions: 0, pending_bookings: 0, urgent_requests: 0, waitlisted: 0, changes_waiting: 0,
          due_soon: [], due_soon_hours: 6, unfreeze_requests: 0, out_of_service: [], today: [], today_count: 0, missed_today: 0, can_decide_urgent: api.role === 'MANAGER' })
      }
      if (path === 'admin/bookings/') {
        if (api.recordsGate) await api.recordsGate
        if (api.roomFail || api.recordsFail) return failure()
        return list(url.searchParams.get('status') === 'APPROVED' ? [booking] : [booking, pending])
      }
      if (path === 'admin/bookings/export/') {
        api.exports.push(url.search)
        return route.fulfill({ contentType: 'text/csv', body: 'Status\nAPPROVED\n' })
      }
      unexpected.push(`${route.request().method()} ${path}`)
      return failure()
    })
    await use(api)
    expect(unexpected, 'All API calls stay inside the synthetic fixture').toEqual([])
  }, { auto: true }],
})

function gate() {
  let release!: () => void
  const promise = new Promise<void>(resolveGate => { release = resolveGate })
  return { promise, release }
}

async function screenshot(page: Page, name: string, width: number) {
  const phase = process.env.FLUENCY_PHASE
  if (!phase) return
  const directory = resolve(process.env.FLUENCY_OUTPUT ?? '../..', ...(process.env.FLUENCY_OUTPUT ? [] : ['output', 'fluency-2026-10-27']), phase)
  await mkdir(directory, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: resolve(directory, `${name}-${width}.png`), fullPage: true, animations: 'disabled' })
}

for (const width of [320, 390, 1440]) {
  test(`V2 filters stay outside resource tabs and fully visible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/#/resources')
    const people = page.getByLabel('Fits at least this many people')
    await expect(people).toBeVisible()
    await screenshot(page, 'V2-people', width)
    const errors: string[] = []
    const inspect = async (selector: string) => {
      const measurements = await page.locator(selector).evaluateAll(elements => elements.map(element => {
        const bounds = element.getBoundingClientRect()
        return { left: bounds.left, right: bounds.right, width: innerWidth }
      }))
      for (const bounds of measurements) if (bounds.left < 0 || bounds.right > bounds.width) errors.push(`${selector} is outside viewport: ${JSON.stringify(bounds)}`)
    }
    await inspect('.bk-people-filter')
    const tabs = page.getByRole('tablist', { name: 'Resource type' })
    if (await tabs.locator(':scope > :not([role="tab"])').count()) errors.push('Resource type tablist contains non-tab filters')
    await tabs.getByRole('tab', { name: /Equipment/ }).click()
    await screenshot(page, 'V2-equipment', width)
    await inspect('.bk-room-filter')
    if (await tabs.locator(':scope > :not([role="tab"])').count()) errors.push('Equipment tablist contains the room filter')
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width)
    expect(errors).toEqual([])
  })
}

for (const width of [390, 1440]) {
  test(`V4 pending records retain dimmed rows and disable output at ${width}px`, async ({ page, api }) => {
    api.role = 'ADMIN'
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/#/admin/records')
    const table = page.getByRole('table', { name: 'Bookings', exact: true })
    await expect(table.locator('tbody tr')).toHaveCount(2)
    const delayed = gate()
    api.recordsGate = delayed.promise
    try {
      await page.getByLabel('Status', { exact: true }).selectOption('APPROVED')
      await screenshot(page, 'V4-updating', width)
      await expect(page.getByText('Updating…', { exact: true })).toBeVisible()
      await expect(table).toHaveAttribute('aria-busy', 'true')
      expect(await table.evaluate(element => Number(getComputedStyle(element).opacity))).toBeLessThan(1)
      await expect(table.locator('tbody tr')).toHaveCount(2)
      await expect(page.getByRole('button', { name: 'Print', exact: true })).toBeDisabled()
      await expect(page.getByRole('button', { name: 'Export CSV', exact: true })).toBeDisabled()
    } finally { delayed.release(); api.recordsGate = null }
    await expect(page.getByText('Updating…', { exact: true })).toHaveCount(0)
    await expect(table).toHaveAttribute('aria-busy', 'false')
    await expect(table.locator('tbody tr')).toHaveCount(1)
    await expect(page.getByText('1 booking', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Print', exact: true })).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Export CSV', exact: true })).toBeEnabled()
    api.recordsFail = true
    await page.getByLabel('Status', { exact: true }).selectOption('WAITLISTED')
    await expect(page.getByRole('alert')).toContainText('Test connection unavailable.')
    await expect(page.getByRole('button', { name: 'Print', exact: true })).toBeEnabled()
    await expect(page.getByRole('button', { name: 'Export CSV', exact: true })).toBeEnabled()
    await expect(table.locator('tbody tr')).toHaveCount(1)
    await page.getByRole('button', { name: 'Export CSV', exact: true }).click()
    await expect.poll(() => api.exports.length).toBe(1)
    expect(new URLSearchParams(api.exports[0]).get('status')).toBe('APPROVED')
  })

  test(`V6 first room load failure has a text retry without Loading at ${width}px`, async ({ page, api }) => {
    api.role = 'MANAGER'; api.roomFail = true
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/#/manager/bookings')
    await expect(page.getByRole('alert')).toContainText('Test connection unavailable.')
    await screenshot(page, 'V6-room-error', width)
    await expect(page.getByText('Loading…', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Try again', exact: true })).toBeVisible()
    api.roomFail = false
    await page.getByRole('button', { name: 'Try again', exact: true }).click()
    await expect(page.getByRole('cell', { name: 'Lab Room 1' }).first()).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('Updated just now', { exact: true })).toBeVisible()
  })

  test(`V8 route content has no entry animation and reduced motion stays effective at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await page.goto('/#/resources')
    await expect(page.getByRole('heading', { name: 'Book a resource', exact: true })).toBeVisible()
    await screenshot(page, 'V8-route', width)
    await expect(page.locator('.app-page')).toHaveCSS('animation-name', 'none')
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await expect(page.locator('.app-page')).toHaveCSS('animation-name', 'none')
    await expect(page.getByRole('button', { name: 'Search', exact: true })).toHaveCSS('transition-duration', '0s')
  })

  for (const role of ['STUDENT', 'ADMIN', 'MANAGER'] as const) {
    test(`V5 ${role} home appears with delayed announcements without shifting at ${width}px`, async ({ page, api }) => {
      api.role = role; api.announcementsDelay = 1600
      await page.setViewportSize({ width, height: 900 })
      const selector = role === 'STUDENT' ? '.dash-stats' : '.today-grid'
      // Record the first painted content position, including the old premature render.
      await page.addInitScript((target) => {
        const probe = () => {
          const element = document.querySelector(target)
          if (element?.getBoundingClientRect().height) {
            document.documentElement.dataset.firstContentY = String(element.getBoundingClientRect().top)
          } else requestAnimationFrame(probe)
        }
        requestAnimationFrame(probe)
      }, selector)
      await page.goto(role === 'STUDENT' ? '/#/dashboard' : '/#/admin/today')
      await expect(page.getByRole('region', { name: 'Announcements', exact: true })).toBeVisible()
      await expect(page.locator(selector)).toBeVisible()
      await screenshot(page, `V5-${role.toLowerCase()}-home`, width)
      const positions = await page.locator(selector).evaluate(element => ({ first: Number(document.documentElement.dataset.firstContentY), current: element.getBoundingClientRect().top }))
      expect(Math.abs(positions.current - positions.first), 'Home content must not shift when announcements arrive').toBe(0)
    })
  }
}

for (const role of ['STUDENT', 'ADMIN', 'MANAGER'] as const) {
  test(`V5 ${role} announcement failure allows home and retry, empty notices leave no region`, async ({ page, api }) => {
    api.role = role; api.announcementsFail = true
    await page.goto(role === 'STUDENT' ? '/#/dashboard' : '/#/admin/today')
    const content = page.locator(role === 'STUDENT' ? '.dash-stats' : '.today-grid')
    await expect(content).toBeVisible()
    await expect(page.getByRole('button', { name: 'Retry announcements', exact: true })).toBeVisible()
    const initialRequests = api.requests.filter(path => path === 'announcements/').length
    api.announcementsFail = false; api.announcementsEmpty = true
    await page.getByRole('button', { name: 'Retry announcements', exact: true }).click()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByRole('region', { name: 'Announcements', exact: true })).toHaveCount(0)
    await expect(content).toBeVisible()
    expect(api.requests.filter(path => path === 'announcements/')).toHaveLength(initialRequests + 1)
    api.announcementsEmpty = false
    await page.reload()
    await expect(page.getByRole('region', { name: 'Announcements', exact: true })).toBeVisible()
  })

  test(`V5 ${role} waits for home data even when announcements arrive first`, async ({ page, api }) => {
    api.role = role
    const delayed = gate(); api.overviewGate = delayed.promise
    try {
      await page.goto(role === 'STUDENT' ? '/#/dashboard' : '/#/admin/today')
      await expect.poll(() => api.requests.includes('announcements/')).toBe(true)
      // The named announcement is available in the fixture but must not paint ahead of home data.
      await expect(page.getByRole('heading', { name: announcement.title, exact: true })).toHaveCount(0)
    } finally { delayed.release(); api.overviewGate = null }
    await expect(page.getByRole('region', { name: 'Announcements', exact: true })).toBeVisible()
    await expect(page.locator(role === 'STUDENT' ? '.dash-stats' : '.today-grid')).toBeVisible()
  })

  // Claude Code review (2026-10-27): V5 gates only the first paint; a later refresh keeps the announcements in place.
  test(`V5 ${role} refresh keeps the announcements in place`, async ({ page, api }) => {
    api.role = role
    await page.goto(role === 'STUDENT' ? '/#/dashboard' : '/#/admin/today')
    const board = page.getByRole('region', { name: 'Announcements', exact: true })
    await expect(board).toBeVisible()
    const delayed = gate(); api.overviewGate = delayed.promise
    try {
      await page.getByRole('button', { name: role === 'STUDENT' ? 'Refresh overview' : 'Refresh now', exact: true }).click()
      await expect(page.getByText(role === 'STUDENT' ? 'Loading your dashboard…' : 'Refreshing…', { exact: true })).toBeVisible()
      await expect(board).toBeVisible()
    } finally { delayed.release(); api.overviewGate = null }
    await expect(page.locator(role === 'STUDENT' ? '.dash-stats' : '.today-grid')).toBeVisible()
    await expect(board).toBeVisible()
  })
}
