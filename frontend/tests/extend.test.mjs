// 1.24.0 (client, Week 8): extending a booking in progress.
import assert from 'node:assert/strict'
import test from 'node:test'
import { canExtend, extendOptions } from '../src/features/booking/extend.ts'

// 10:00-11:00 Sydney (AEDT, UTC+11) on 10 Jan 2030.
const booking = (extra = {}) => ({ id: 'b1', student_id: 'u1', status: 'APPROVED', start: '2030-01-09T23:00:00Z',
  end: '2030-01-10T00:00:00Z', ...extra })
const room = { slot_minutes: 30, selection_step_minutes: 30, closing_time: '12:00:00', max_booking_minutes: 480 }
const during = Date.parse('2030-01-09T23:30:00Z')

test('only the owner or a Manager, only while the approved booking is in progress', () => {
  assert.equal(canExtend(booking(), 'u1', false, during), true)
  assert.equal(canExtend(booking(), 'u2', false, during), false)
  assert.equal(canExtend(booking(), 'u2', true, during), true)
  assert.equal(canExtend(booking(), 'u1', false, Date.parse('2030-01-09T22:00:00Z')), false) // not started
  assert.equal(canExtend(booking(), 'u1', false, Date.parse('2030-01-10T00:00:00Z')), false) // ended
  assert.equal(canExtend(booking({ status: 'PENDING_APPROVAL' }), 'u1', false, during), false)
  assert.equal(canExtend(booking({ long_booking: true }), 'u1', false, during), false)
})

test('end times follow the time step and stop at closing time and the longest booking', () => {
  assert.deepEqual(extendOptions(booking(), room, 480),
    ['2030-01-10T00:30:00.000Z', '2030-01-10T01:00:00.000Z']) // 11:30, 12:00 (closing)
  assert.deepEqual(extendOptions(booking(), room, 90), ['2030-01-10T00:30:00.000Z']) // up to 1.5 h in total
  assert.deepEqual(extendOptions(booking(), room, 60), [])
})
