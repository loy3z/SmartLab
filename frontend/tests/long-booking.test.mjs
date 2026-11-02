import assert from 'node:assert/strict'
import test from 'node:test'
import { bookingDetail, submittedMessage } from '../src/features/booking/format.ts'
import { canAskForChange } from '../src/features/booking/change-requests.ts'
import { todoCards } from '../src/features/admin/today.ts'

const booking = (extra = {}) => ({ id: 'long-1', student_id: 'u1', start: '2030-01-10T00:00:00Z', end: '2030-01-10T04:00:00Z',
  status: 'PENDING_APPROVAL', long_booking: true, review_due_at: '2030-01-02T00:00:00Z', ...extra })

test('long bookings need a Manager by the review deadline and expire without automatic approval', () => {
  assert.match(bookingDetail(booking()), /Manager to approve it by/)
  assert.match(bookingDetail(booking()), /time is held during review/)
  assert.match(bookingDetail(booking()), /expires if nobody decides/)
  assert.match(bookingDetail(booking()), /never approved automatically/)
  assert.match(bookingDetail(booking({ status: 'EXPIRED' })), /review deadline or requested start/)
  assert.match(submittedMessage(booking()).message, /otherwise it expires/)
})

test('waitlisted longer bookings retain queue order and still require a Manager', () => {
  const waiting = booking({ status: 'WAITLISTED', waitlist_position: 2, reason_code: 'TIME_CONFLICT' })
  assert.match(bookingDetail(waiting), /#2/)
  assert.match(bookingDetail(waiting), /submission order.*Manager/)
  assert.match(submittedMessage(waiting).message, /Manager.*never approved automatically/)
  assert.match(bookingDetail({ ...waiting, long_booking: false }), /admin/)
})

test('approved longer bookings must be cancelled and requested again to change time', () => {
  const approved = booking({ status: 'APPROVED' })
  assert.equal(canAskForChange(approved, 'u1', Date.parse('2030-01-01T00:00:00Z')), false)
  assert.equal(canAskForChange({ ...approved, long_booking: false }, 'u1', Date.parse('2030-01-01T00:00:00Z')), true)
})

test('long-booking overview links to the independent Manager review queue', () => {
  const data = { urgent_requests: 0, pending_bookings: 0, changes_waiting: 0, pending_inductions: 0, unfreeze_requests: 0,
    waitlisted: 0, due_soon: [], long_booking_requests: 2, can_decide_long_bookings: true }
  const card = todoCards(data).find(item => item.key === 'long-bookings')
  assert.equal(card.count, 2)
  assert.equal(card.to, '/admin/bookings?type=long-bookings')
  assert.match(card.hint, /never automatic/)
  assert.equal(todoCards({ ...data, can_decide_long_bookings: false }).find(item => item.key === 'long-bookings').hint, 'Only a Manager can decide these')
})
