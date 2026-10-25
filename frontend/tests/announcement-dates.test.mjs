// Sprint 3 (1.19.0): Sydney estimates/expiry dates are independent of the browser's local time zone.
import test from 'node:test'
import assert from 'node:assert/strict'
import { dateTimeInput, dateTimeISO } from '../src/features/announcements/dates.ts'

test('announcement dates support optional expiry and Sydney winter/summer time', () => {
  assert.equal(dateTimeISO(''), null)
  assert.equal(dateTimeInput(null), '')
  assert.equal(dateTimeISO('2026-10-26T12:30'), '2026-10-26T01:30:00.000Z')
  assert.equal(dateTimeISO('2026-07-26T12:30'), '2026-07-26T02:30:00.000Z')
  assert.equal(dateTimeInput('2026-10-25T23:30:00Z'), '2026-10-26T10:30')
})
test('announcement inputs reject invalid dates and the missing daylight-saving hour', () => {
  assert.throws(() => dateTimeISO('invalid'))
  assert.throws(() => dateTimeISO('2026-10-04T02:30'), /does not exist/)
})
