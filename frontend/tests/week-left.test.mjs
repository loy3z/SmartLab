// 2026-11-10 (U1): the booking window says how many hours are left in the week being booked.
import assert from 'node:assert/strict'
import test from 'node:test'
import { weekLeftText } from '../src/features/booking/week-left.ts'

const week = { week_start: '2026-11-16', used_hours: 10, limit_hours: 12 }

test('names the week and the hours left of the weekly allowance', () => {
  assert.equal(weekLeftText({ week_hours: week }), 'Week of 16 Nov: 2 h left of your 12 h.')
  assert.equal(weekLeftText({ week_hours: { ...week, used_hours: 4.5 } }), 'Week of 16 Nov: 7.5 h left of your 12 h.')
})

test('never shows a negative number', () => {
  assert.equal(weekLeftText({ week_hours: { ...week, used_hours: 13 } }), 'Week of 16 Nov: 0 h left of your 12 h.')
})

test('says nothing when the weekly allowance does not apply', () => {
  assert.equal(weekLeftText(null), '')
  assert.equal(weekLeftText({}), '')
  for (const flag of ['manager_override', 'test_bypass', 'additional_hours', 'long_booking']) {
    assert.equal(weekLeftText({ week_hours: week, [flag]: true }), '', flag)
  }
})
