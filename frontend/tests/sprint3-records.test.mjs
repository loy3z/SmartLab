// Sprint 3: durations in hours, weekly series cards on My Bookings, Booking Records filters.
import assert from 'node:assert/strict'
import test from 'node:test'
import { fmtDuration, fmtRelative } from '../src/features/booking/format.ts'
import { groupBookings, seriesSummary } from '../src/features/booking/my-bookings.ts'
import { addDays, attendanceText, creatorText, defaultRecordFilters, recordQuery, sydneyMidnight } from '../src/features/records/records.ts'

const booking = (id, start, end, overrides = {}) => ({ id, start, end, status: 'APPROVED', series_id: null, ...overrides })

test('booking lengths are shown in hours', () => {
  assert.equal(fmtDuration(30), '0.5 h')
  assert.equal(fmtDuration(60), '1 h')
  assert.equal(fmtDuration(90), '1.5 h')
  assert.equal(fmtDuration(120), '2 h')
  assert.equal(fmtDuration(45), '0.75 h')
  assert.equal(fmtDuration(15), '0.25 h')
})

test('relative times keep hours and minutes', () => {
  const now = Date.parse('2030-01-10T00:00:00Z')
  assert.equal(fmtRelative('2030-01-10T01:30:00Z', now), 'in 1 h 30 min')
  assert.equal(fmtRelative('2030-01-09T23:15:00Z', now), '45 min ago')
})

test('a weekly series becomes one group, in list order, with dates sorted', () => {
  // Sydney is UTC+11 in January: 22:00Z the day before is 09:00 local.
  const list = [
    booking('s2', '2030-01-15T22:00:00Z', '2030-01-15T23:00:00Z', { series_id: 'S' }), // Wed 16 Jan
    booking('one', '2030-01-20T00:00:00Z', '2030-01-20T01:00:00Z'),
    booking('s1', '2030-01-13T22:00:00Z', '2030-01-13T23:00:00Z', { series_id: 'S' }), // Mon 14 Jan
    booking('s3', '2030-01-20T22:00:00Z', '2030-01-20T23:00:00Z', { series_id: 'S', status: 'CANCELLED' }), // Mon 21 Jan
  ]
  const groups = groupBookings(list)
  assert.deepEqual(groups.map((group) => group.kind), ['series', 'single'])
  assert.deepEqual(groups[0].bookings.map((item) => item.id), ['s1', 's2', 's3'])
  const summary = seriesSummary(groups[0].bookings, Date.parse('2030-01-14T23:30:00Z')) // after Monday's date
  assert.equal(summary.pattern, 'Every Mon, Wed · 9:00 am – 10:00 am')
  assert.deepEqual([summary.total, summary.remaining, summary.cancelled, summary.next?.id], [3, 1, 1, 's2'])
})

test('a series with a moved date says the times vary', () => {
  const dates = [
    booking('a', '2030-01-13T22:00:00Z', '2030-01-13T23:00:00Z', { series_id: 'S' }),
    booking('b', '2030-01-20T23:00:00Z', '2030-01-21T00:00:00Z', { series_id: 'S' }),
  ]
  const summary = seriesSummary(dates, Date.parse('2030-01-01T00:00:00Z'))
  assert.equal(summary.pattern, 'Every Mon · 9:00 am – 10:00 am (times vary)')
  assert.equal(seriesSummary(dates, Date.parse('2030-02-01T00:00:00Z')).next, null)
})

test('Sydney midnight carries the right offset across daylight saving', () => {
  assert.equal(sydneyMidnight('2030-01-10'), '2030-01-10T00:00:00+11:00')
  assert.equal(sydneyMidnight('2030-07-10'), '2030-07-10T00:00:00+10:00')
  assert.equal(sydneyMidnight('2026-10-04'), '2026-10-04T00:00:00+10:00') // daylight saving starts at 2 am that day
  assert.equal(sydneyMidnight('2026-10-05'), '2026-10-05T00:00:00+11:00')
  assert.equal(addDays('2030-12-31', 1), '2031-01-01')
})

test('record filters become the API query (both dates included)', () => {
  const filters = { ...defaultRecordFilters('2030-01-31'), resourceId: 'r1', q: '  z500 ' }
  assert.deepEqual([filters.from, filters.to, filters.status], ['2030-01-01', '2030-03-02', 'ALL'])
  const query = Object.fromEntries(recordQuery({ ...filters, to: '2030-01-31' }))
  assert.deepEqual(query, { status: 'ALL', since: '2030-01-01T00:00:00+11:00', until: '2030-02-01T00:00:00+11:00', resource_id: 'r1', q: 'z500' })
  assert.equal(recordQuery({ from: '', to: '', resourceId: '', q: ' ', status: 'APPROVED' }).toString(), 'status=APPROVED')
})

test('record columns: creator and attendance', () => {
  assert.equal(creatorText({ on_behalf: false }), 'Self')
  assert.equal(creatorText({ on_behalf: true, created_by_user: { display_name: 'Demo administrator', zid: 'z9000001' } }), 'Demo administrator (z9000001)')
  assert.equal(attendanceText({ status: 'REJECTED' }), '—')
  assert.equal(attendanceText({ status: 'APPROVED', attendance: null }), 'Not yet')
  assert.equal(attendanceText({ status: 'APPROVED', attendance: 'NO_SHOW' }), 'Missed (no check-in)')
  assert.equal(attendanceText({ status: 'APPROVED', attendance: 'NOT_TRACKED' }), 'Not tracked')
})
