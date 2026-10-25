// Sprint 3: calendar link, notifications, check-in and weekly series helpers.
import assert from 'node:assert/strict'
import test from 'node:test'
import { badgeText, notificationTarget, notificationTone } from '../src/features/notifications/notifications.ts'
import { ATTENDANCE_TEXT, calendarUrl, canCheckIn, checkInHint } from '../src/features/booking/attendance.ts'
import { addDaysIso, isoWeekday, problemDates, startTimes } from '../src/features/booking/series.ts'

const booking = (overrides = {}) => ({
  id: 'b1', student_id: 'u1', status: 'APPROVED', attendance: null, check_in_open: false,
  check_in_opens_at: '2030-01-10T00:45:00Z', check_in_closes_at: '2030-01-10T01:30:00Z', ...overrides,
})

test('bell badge text', () => {
  assert.equal(badgeText(0), '')
  assert.equal(badgeText(7), '7')
  assert.equal(badgeText(150), '99+')
})

test('notification links stay inside the app', () => {
  assert.equal(notificationTarget({ link: '/admin/bookings' }), '/admin/bookings')
  assert.equal(notificationTarget({ link: 'https://evil.example/x' }), '/bookings')
  assert.equal(notificationTarget({ link: '//evil.example' }), '/bookings')
  assert.equal(notificationTarget({ link: null }), '/bookings')
})

test('notification tone', () => {
  assert.equal(notificationTone('BOOKING_APPROVED'), 'good')
  assert.equal(notificationTone('UNFREEZE_REJECTED'), 'bad')
  assert.equal(notificationTone('ACCOUNT_FROZEN'), 'bad')
  assert.equal(notificationTone('URGENT_REQUEST'), 'info')
})

test('only the person booked for checks in while the window is open', () => {
  assert.equal(canCheckIn(booking({ check_in_open: true }), 'u1'), true)
  assert.equal(canCheckIn(booking({ check_in_open: true }), 'staff'), false)
  assert.equal(canCheckIn(booking(), 'u1'), false)
  assert.equal(ATTENDANCE_TEXT.NO_SHOW, 'Missed (no check-in)')
})

test('check-in hint until the window closes', () => {
  const fmt = (iso) => iso.slice(11, 16)
  assert.match(checkInHint(booking(), Date.parse('2030-01-09T00:00:00Z'), fmt), /between 00:45 and 01:30/)
  assert.equal(checkInHint(booking(), Date.parse('2030-01-10T02:00:00Z'), fmt), '')
  assert.equal(checkInHint(booking({ attendance: 'CHECKED_IN' }), 0, fmt), '')
})

test('calendar link is absolute on the same site', () => {
  assert.equal(calendarUrl('/api/v1/calendar/abc.ics', 'http://localhost:5173/'), 'http://localhost:5173/api/v1/calendar/abc.ics')
})

test('series helpers', () => {
  assert.equal(addDaysIso('2030-01-31', 1), '2030-02-01')
  assert.equal(isoWeekday('2030-01-07'), 1)
  assert.equal(isoWeekday('2030-01-13'), 7)
  assert.deepEqual(problemDates([{ date: 'a', available: true }, { date: 'b', available: false }]), ['b'])
  assert.deepEqual(startTimes('08:00:00', '09:30:00', 30), ['08:00', '08:30', '09:00'])
})

test('reminder and expiry tones', () => {
  assert.equal(notificationTone('BOOKING_REMINDER'), 'info')
  assert.equal(notificationTone('INDUCTION_EXPIRING'), 'info')
  assert.equal(notificationTone('BOOKING_EXPIRED'), 'bad')
})
