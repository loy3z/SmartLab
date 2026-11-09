// 2026-11-07 (client, Week 8): the three roles see different home pages and data.
import assert from 'node:assert/strict'
import test from 'node:test'
import { cardsFor, MANAGER_DECIDES } from '../src/features/admin/today.ts'
import { busiest, cleanZid, currentWeek, segments, statusCounts } from '../src/features/manager/manager-home.ts'
import { ADMIN_HISTORY_DAYS, defaultRecordFilters } from '../src/features/records/records.ts'
import { homePath } from '../src/app/routes.ts'
import { statusText } from '../src/features/booking/format.ts'

const overview = (role) => ({ role, pending_inductions: 1, pending_bookings: 2, urgent_requests: 1, waitlisted: 0, changes_waiting: 0,
  due_soon: [], due_soon_hours: 6, out_of_service: [], today: [], today_count: 0, missed_today: 0, can_decide_urgent: role === 'MANAGER',
  additional_hours_requests: 1, long_booking_requests: 1 })

test('each role starts on its own home page', () => {
  assert.equal(homePath('STUDENT'), '/dashboard')
  assert.equal(homePath('ADMIN'), '/admin/today')
  assert.equal(homePath('MANAGER'), '/manager/home')
})

test('Today shows an Admin only review work; a Manager sees every card', () => {
  const admin = cardsFor(overview('ADMIN')).map((card) => card.key)
  assert.ok(MANAGER_DECIDES.every((key) => !admin.includes(key)))
  assert.ok(admin.includes('bookings') && admin.includes('inductions'))
  const manager = cardsFor(overview('MANAGER')).map((card) => card.key)
  assert.ok(MANAGER_DECIDES.every((key) => manager.includes(key)))
})

test('Booking records: Admins start from the last 7 days; a Manager lookup covers a year', () => {
  assert.equal(ADMIN_HISTORY_DAYS, 7)
  assert.equal(defaultRecordFilters('2030-01-31', false).from, '2030-01-24')
  assert.equal(defaultRecordFilters('2030-01-31', true).from, '2030-01-01')
  const lookup = defaultRecordFilters('2030-01-31', true, 'z5123456')
  assert.deepEqual([lookup.from, lookup.q], ['2029-01-31', 'z5123456'])
  assert.equal(defaultRecordFilters('2030-01-31', false, 'z5123456').from, '2030-01-24') // an Admin keeps the limit
})

test('Manager home helpers: week, status counts, zID', () => {
  assert.deepEqual(currentWeek('2030-01-09'), { first: '2030-01-07', last: '2030-01-13' }) // a Wednesday
  assert.deepEqual(currentWeek('2030-01-13'), { first: '2030-01-07', last: '2030-01-13' }) // a Sunday
  const resources = [{ active: true, status: 'AVAILABLE' }, { active: true, status: 'MAINTENANCE' }, { active: false, status: 'CLOSED' }]
  assert.deepEqual(statusCounts(resources), { AVAILABLE: 1, MAINTENANCE: 1, CLOSED: 0 })
  assert.equal(cleanZid(' Z5123456 '), 'z5123456')
  assert.equal(cleanZid('5123456'), null)
})

test('waiting requests name who decides: a Manager for urgent, additional-hours and longer requests', () => {
  const pending = { status: 'PENDING_APPROVAL' }
  assert.equal(statusText(pending), 'Waiting for admin approval')
  for (const kind of ['urgent', 'additional_hours', 'long_booking']) {
    assert.equal(statusText({ ...pending, [kind]: true }), 'Waiting for Manager approval', kind)
  }
  assert.equal(statusText({ status: 'APPROVED', urgent: true }), 'Approved')
})

test('the Extension requests card opens the approval list', async () => {
  const { todoCards } = await import('../src/features/admin/today.ts')
  const card = todoCards(overview('MANAGER')).find((item) => item.key === 'extensions')
  assert.equal(card.to, '/manager/home?focus=extensions')
})

// 2026-11-09 (Loy feedback): the Lab overview shows split bars and the most booked resources.
test('a split bar leaves out empty parts and shows nothing when everything is 0', () => {
  const parts = [{ label: 'open', count: 3, color: 'g' }, { label: 'under maintenance', count: 0, color: 'a' }, { label: 'closed', count: 1, color: 'r' }]
  assert.deepEqual(segments(parts).map(({ label, share }) => [label, share]), [['open', 75], ['closed', 25]])
  assert.deepEqual(segments(parts.map((part) => ({ ...part, count: 0 }))), [])
})

test('the most booked resources come first, scaled to the busiest, and unbooked ones are left out', () => {
  const row = (resource_id, name, booked_hours) => ({ resource_id, name, booked_hours })
  const rows = [row('a', 'Microscope', 2), row('b', 'Lab Room 1', 8), row('c', 'Printer', 0), row('d', 'Bench', 2)]
  assert.deepEqual(busiest(rows), [
    { id: 'b', name: 'Lab Room 1', hours: 8, share: 100 },
    { id: 'd', name: 'Bench', hours: 2, share: 25 },
    { id: 'a', name: 'Microscope', hours: 2, share: 25 },
  ])
  assert.equal(busiest(rows, 1).length, 1)
  assert.deepEqual(busiest([]), [])
})

