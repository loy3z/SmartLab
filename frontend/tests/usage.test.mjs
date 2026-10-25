// Sprint 3: display helpers of the Manager usage report.
import assert from 'node:assert/strict'
import test from 'node:test'
import { lastFourWeeks, percent, sortUsage } from '../src/features/manager/usage.ts'

test('percent and default range', () => {
  assert.equal(percent(0.256), '26%')
  assert.equal(percent(null), '—')
  assert.deepEqual(lastFourWeeks('2030-03-01'), { first: '2030-02-02', last: '2030-03-01' })
})

test('busiest resources first', () => {
  const rows = [{ name: 'B', booked_hours: 1 }, { name: 'A', booked_hours: 5 }, { name: 'C', booked_hours: 1 }]
  assert.deepEqual(sortUsage(rows).map((row) => row.name), ['A', 'B', 'C'])
})
