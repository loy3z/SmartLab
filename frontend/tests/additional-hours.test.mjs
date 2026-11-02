import assert from 'node:assert/strict'
import test from 'node:test'
import { additionalHoursPriority, compareAdditionalHours } from '../src/features/booking/additional-hours.ts'
import { bookingDetail, submittedMessage } from '../src/features/booking/format.ts'
import { canAskForChange } from '../src/features/booking/change-requests.ts'
import { todoCards } from '../src/features/admin/today.ts'
import { notificationTone } from '../src/features/notifications/notifications.ts'

const request = (id, created, reasons, extra = {}) => ({
  id, created_at: created, start: '2030-01-10T00:00:00Z', end: '2030-01-10T01:00:00Z',
  student_id: 'student', status: 'PENDING_APPROVAL', additional_hours: true,
  additional_hours_review: { approval_opens_at: '2030-01-08T00:00:00Z', approval_window_hours: 48,
    priority_group: reasons.length ? 'PRIORITY' : 'STANDARD', priority_reasons: reasons, queue_position: 1,
    can_approve: true, blocker_code: null, blocker_message: null }, ...extra,
})

test('additional hours: both priority reasons are equal and ties use submission order', () => {
  const unused = request('b', '2030-01-01T02:00:00Z', ['NO_USE_THIS_WEEK'])
  const collecting = request('a', '2030-01-01T01:00:00Z', ['ACTIVE_DATA_COLLECTION'])
  const both = request('c', '2030-01-01T03:00:00Z', ['NO_USE_THIS_WEEK', 'ACTIVE_DATA_COLLECTION'])
  const ordinary = request('d', '2030-01-01T00:00:00Z', [])
  assert.deepEqual([ordinary, both, unused, collecting].sort(compareAdditionalHours).map(item => item.id), ['a', 'b', 'c', 'd'])
  assert.equal(additionalHoursPriority(unused), 'No recorded lab use this week')
  assert.match(additionalHoursPriority(collecting), /Manager confirmation required/)
  assert.equal(additionalHoursPriority(ordinary), 'Standard priority')
})

test('additional-hours pending and submission copy never promises a hold or automatic approval', () => {
  const booking = request('a', '2030-01-01T00:00:00Z', [])
  assert.match(bookingDetail(booking), /waiting for a Manager/)
  assert.match(bookingDetail(booking), /does not hold the time/)
  assert.match(bookingDetail(booking), /never approved automatically/)
  assert.match(bookingDetail(booking), /expires if not approved before the start/)
  assert.match(submittedMessage(booking).message, /Approval opens/)
  assert.match(submittedMessage(booking).message, /time is not reserved/)
})

test('additional hours grant only the requested time; ordinary changes remain available', () => {
  const booking = request('a', '2030-01-01T00:00:00Z', [], { status: 'APPROVED' })
  assert.equal(canAskForChange(booking, 'student', Date.parse('2030-01-01T00:00:00Z')), false)
  assert.equal(canAskForChange({ ...booking, additional_hours: false }, 'student', Date.parse('2030-01-01T00:00:00Z')), true)
})

test('additional-hours overview and notifications distinguish manual review from normal bookings', () => {
  const base = { urgent_requests: 0, pending_bookings: 0, changes_waiting: 0, pending_inductions: 0, unfreeze_requests: 0,
    waitlisted: 0, due_soon: [], additional_hours_requests: 3, additional_hours_ready: 1, can_decide_additional_hours: true }
  const card = todoCards(base).find(item => item.key === 'additional-hours')
  assert.equal(card.count, 3)
  assert.equal(card.hint, '1 ready for Manager approval')
  assert.equal(card.to, '/admin/bookings?type=additional-hours')
  assert.match(todoCards({ ...base, can_decide_additional_hours: false }).find(item => item.key === 'additional-hours').hint, /do not hold time/)
  assert.equal(notificationTone('ADDITIONAL_HOURS_REQUEST'), 'info')
  assert.equal(notificationTone('ADDITIONAL_HOURS_APPROVED'), 'good')
  assert.equal(notificationTone('ADDITIONAL_HOURS_EXPIRED'), 'bad')
})
