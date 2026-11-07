// 2026-11-07 (client, Week 8): the three roles see different home pages and data.
import assert from 'node:assert/strict'
import test from 'node:test'
import { cardsFor, MANAGER_DECIDES } from '../src/features/admin/today.ts'
import { cleanZid, currentWeek, statusCounts } from '../src/features/manager/manager-home.ts'
import { ADMIN_HISTORY_DAYS, defaultRecordFilters } from '../src/features/records/records.ts'
import { homePath } from '../src/app/routes.ts'

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
