// Sprint 3: maintenance card A (M1①, B1, V3) acceptance; every API response is synthetic and intercepted.
import { expect, test as base } from '@playwright/test'

const room = {
  id: 'room-1', name: 'Lab Room 1', kind: 'ROOM', location: 'Demo laboratory', description: '', active: true,
  required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00:00', closing_time: '20:00:00',
  timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE', status_reason: null, room_id: null, category: null,
  capacity: 12, details: [],
}
const person = (id: string, display_name: string) => ({ id, zid: `z${id.slice(-7).padStart(7, '0')}`, display_name })
const booking = (id: string, status: string, student: ReturnType<typeof person>, day: number) => ({
  id, resource_id: room.id, student_id: student.id, created_by: null, series_id: null, status,
  start: `2030-11-0${day}T00:00:00Z`, end: `2030-11-0${day}T01:00:00Z`, created_at: '2030-10-20T00:00:00Z', revision: 1,
  purpose: 'Synthetic practical session', reason_code: null, decision_reason: null, replaces_id: null, student, attendance: null,
})
const bookings = [
  booking('bk-approved', 'APPROVED', person('student-1', 'Confirmed Student'), 3),
  booking('bk-pending', 'PENDING_APPROVAL', person('student-2', 'Pending Student'), 4),
  booking('bk-waitlisted', 'WAITLISTED', person('student-3', 'Queued Student'), 5),
]
interface Api {
  room: typeof room
  bookingQueries: URLSearchParams[]
  refreshGate: Promise<void> | null
}
const test = base.extend<{ api: Api }>({
  api: [async ({ page }, use) => {
    const api: Api = { room: { ...room }, bookingQueries: [], refreshGate: null }
    const unexpected: string[] = []
    await page.addInitScript(() => localStorage.setItem('access_token', 'synthetic-maintenance-session'))
    await page.route('**/api/v1/**', async route => {
      const request = route.request(), url = new URL(request.url()), path = url.pathname.replace('/api/v1/', '')
      const json = (data: unknown, status = 200) => route.fulfill({ json: data, status })
      if (path === 'auth/me/') return json({ id: 'manager-1', zid: 'z9000001', display_name: 'Test Manager', role: 'MANAGER', university_email: 'manager@example.test', active: true })
      if (path === 'auth/config/') return json({ mode: 'demo', demo_auth_enabled: true, staff_sign_in_enabled: true })
      if (path === 'notifications/') return json({ count: 0, unread_count: 0, results: [] })
      if (path === 'resources/') return json({ count: 1, results: [api.room] })
      if (path === 'admin/bookings/' && request.method() === 'GET') {
        api.bookingQueries.push(url.searchParams)
        if (api.refreshGate) await api.refreshGate
        // Like the real API: only the requested statuses come back.
        const statuses = (url.searchParams.get('status') ?? 'PENDING_APPROVAL').split(',')
        const results = bookings.filter(item => statuses.includes(item.status))
        return json({ count: results.length, results })
      }
      if (path === 'admin/resources/room-1/status/' && request.method() === 'PATCH') {
        const body = request.postDataJSON()
        api.room = { ...api.room, status: body.status, status_reason: body.reason || null }
        return json({ resource: api.room, affected_bookings: bookings })
      }
      unexpected.push(`${request.method()} ${path}`)
      return json({ error: { code: 'SYNTHETIC_FAILURE', message: 'Unexpected request.', details: {} } }, 500)
    })
    await use(api)
    expect(unexpected, 'All API calls stay inside the synthetic fixture').toEqual([])
  }, { auto: true }],
})

const roomsTable = (page: import('@playwright/test').Page) => page.getByRole('table').first()

test('M1: Room management asks only for bookings and requests that have not ended', async ({ page, api }) => {
  const before = Date.now()
  await page.goto('/#/manager/bookings')
  await expect(roomsTable(page).getByRole('row', { name: /Lab Room 1/ })).toBeVisible()
  const query = api.bookingQueries[0]
  expect(query.get('status')?.split(',').sort()).toEqual(['APPROVED', 'PENDING_APPROVAL', 'WAITING_QUALIFICATION', 'WAITLISTED'])
  const since = Date.parse(query.get('since') ?? '')
  expect(since, 'since is the time the page asked').toBeGreaterThanOrEqual(before - 1000)
  expect(since).toBeLessThanOrEqual(Date.now())
})

test('B1: the status dialog counts requests too, while the table lists only confirmed bookings', async ({ page }) => {
  await page.goto('/#/manager/bookings')
  const row = roomsTable(page).getByRole('row', { name: /Lab Room 1/ })
  await expect(row).toBeVisible()
  await expect(page.getByText('Confirmed Student', { exact: true })).toBeVisible()
  await expect(page.getByText('Pending Student')).toHaveCount(0)
  await expect(page.getByText('Queued Student')).toHaveCount(0)
  await expect(row.getByRole('cell').nth(3)).toHaveText('1')
  await row.getByRole('button', { name: 'Maintenance', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Put Lab Room 1 under maintenance?', exact: true })
  await expect(dialog).toContainText('3 upcoming bookings and requests affected.')
  await expect(dialog).toContainText('Pending Student')
  await expect(dialog).toContainText('Queued Student')
})

test('V3: after saving, the room shows its new status at once and cannot be changed again until the page has refreshed', async ({ page, api }) => {
  await page.goto('/#/manager/bookings')
  const row = roomsTable(page).getByRole('row', { name: /Lab Room 1/ })
  await row.getByRole('button', { name: 'Maintenance', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Put Lab Room 1 under maintenance?', exact: true })
  await dialog.getByLabel('Reason (shown to students)', { exact: true }).fill('Replacing the fume hood')
  let release!: () => void
  api.refreshGate = new Promise<void>(resolve => { release = resolve })
  try {
    await dialog.getByRole('button', { name: 'Start maintenance', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await expect(row.getByRole('cell').nth(1)).toHaveText('Maintenance')
    await expect(row.getByRole('button', { name: 'Close', exact: true })).toHaveCount(0)
    await expect(row.getByRole('button', { name: 'Reopen', exact: true })).toBeDisabled()
  } finally { release(); api.refreshGate = null }
  await expect(row.getByRole('button', { name: 'Reopen', exact: true })).toBeEnabled()
  await expect(row).toContainText('Replacing the fume hood')
})
