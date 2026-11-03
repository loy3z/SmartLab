// Sprint 3 (1.16.0): helpers behind the fixes from the user review (change requests, Find a free time, forms,
// contact details, induction guidance, Lab setup and the staff Today page).
import assert from 'node:assert/strict'
import test from 'node:test'
import { canAskForChange, changeSentMessage, openChangeText, replacesText } from '../src/features/booking/change-requests.ts'
import { findDurations, hiddenSummary } from '../src/features/booking/find-time.ts'
import { errorMessage, SEPARATE_BOOKING_TEXT, submitBlocker } from '../src/features/booking/format.ts'
import { changedFields, checkResource, describeHours, emptyResource, hoursFromMinutes, minutesFromHours } from '../src/features/manager/resource-form.ts'
import { hasContact, mailtoLink } from '../src/features/contact/contact.ts'
import { guideItems } from '../src/features/induction/guide.ts'
import { emptyRequirement, requirementChanges } from '../src/features/manager/lab-setup.ts'
import { attendanceLabel, todoCards } from '../src/features/admin/today.ts'

const NOW = Date.parse('2030-01-05T00:00:00Z')
const booking = (overrides = {}) => ({
  id: 'b1', student_id: 'u1', resource_id: 'r1', status: 'APPROVED', start: '2030-01-10T00:00:00Z', end: '2030-01-10T01:00:00Z',
  attendance: null, open_change: null, replaces_booking: null, ...overrides,
})

test('change requests: offered on the person\'s own future approved booking without a change waiting', () => {
  assert.equal(canAskForChange(booking(), 'u1', NOW), true)
  assert.equal(canAskForChange(booking(), 'u2', NOW), false)
  assert.equal(canAskForChange(booking({ status: 'PENDING_APPROVAL' }), 'u1', NOW), false)
  assert.equal(canAskForChange(booking({ start: '2030-01-01T00:00:00Z' }), 'u1', NOW), false)
  const waiting = { id: 'c1', start: '2030-01-11T00:00:00Z', end: '2030-01-11T01:00:00Z', status: 'WAITLISTED' }
  assert.equal(canAskForChange(booking({ open_change: waiting }), 'u1', NOW), false)
  assert.match(openChangeText(booking({ open_change: waiting })), /^Change requested: .* · Waitlisted$/)
  assert.match(replacesText(booking({ replaces_booking: { ...waiting, status: 'APPROVED' } })), /stays until this one is approved/)
  assert.equal(replacesText(booking()), '')
  assert.equal(changeSentMessage(booking({ status: 'WAITLISTED' })).title, 'Change on the waitlist')
  assert.equal(changeSentMessage(booking({ status: 'PENDING_APPROVAL', review_due_at: null })).title, 'Change requested')
  assert.equal(changeSentMessage(booking()).title, 'Booking moved')
  assert.match(changeSentMessage(booking()).message, /old time has been released/)
})

test('Find a free time: lengths stop at the longest normal booking allowed, and why rows are hidden', () => {
  assert.deepEqual(findDurations(), [30, 60, 90, 120, 150, 180])
  assert.deepEqual(findDurations(120), [30, 60, 90, 120])
  assert.deepEqual(findDurations(240), [30, 60, 90, 120, 150, 180, 240])
  assert.deepEqual(hiddenSummary(undefined), { text: '', needsInduction: false })
  assert.deepEqual(hiddenSummary({ MAINTENANCE: 1, NOT_SUBMITTED: 18 }),
    { text: '19 hidden: 18 induction not submitted, 1 under maintenance', needsInduction: true })
  assert.deepEqual(hiddenSummary({ FROZEN: 3 }), { text: '3 hidden: 3 your booking is frozen', needsInduction: false })
})

test('booking-window errors show the configured limit without inventing a fallback', () => {
  assert.equal(errorMessage({ code: 'BOOKING_TOO_FAR_AHEAD', details: { latest_date: '2030-01-29', max_advance_days: 28 } }),
    'Bookings can be made at most 28 days ahead. The latest date you can book is 29 Jan 2030.')
  assert.equal(errorMessage({ code: 'BOOKING_TOO_FAR_AHEAD', details: { latest_date: '2030-01-15', max_advance_days: 14 } }),
    'Bookings can be made at most 14 days ahead. The latest date you can book is 15 Jan 2030.')
  assert.equal(errorMessage({ code: 'BOOKING_TOO_FAR_AHEAD', details: { latest_date: '2030-01-15' } }),
    'The latest date you can book is 15 Jan 2030.')
})

test('the booking form says what is still missing, in order', () => {
  const ready = { ready: true, canRequest: true, hasTime: true, hasPurpose: true, needsReason: false }
  assert.equal(submitBlocker(ready), '')
  assert.equal(submitBlocker({ ...ready, hasPurpose: false }), 'Add a purpose to send the request.')
  assert.equal(submitBlocker({ ...ready, hasTime: false, hasPurpose: false }), 'Choose a time above.')
  assert.equal(submitBlocker({ ...ready, ready: false }), 'Check the zID first.')
  assert.match(SEPARATE_BOOKING_TEXT.ROOM, /does not include the equipment/)
})

test('resource form: hours, capacity and details', () => {
  assert.equal(hoursFromMinutes(90), 1.5)
  assert.equal(minutesFromHours(1.5), 90)
  assert.equal(describeHours(1440), '24 h (1 day)')
  assert.equal(describeHours(90), '1.5 h')
  const form = { ...emptyResource('req-1'), name: 'Room', location: 'K17' }
  assert.deepEqual(checkResource('ROOM', { ...form, capacity: 12, details: [{ label: 'Floor', value: '3' }, { label: '', value: '' }] }), {})
  assert.ok(checkResource('EQUIPMENT', { ...form, capacity: 3 }).capacity)
  assert.ok(checkResource('ROOM', { ...form, capacity: 0 }).capacity)
  assert.ok(checkResource('ROOM', { ...form, details: [{ label: 'Model', value: '' }] }).details)
  assert.ok(checkResource('ROOM', { ...form, details: Array.from({ length: 13 }, (_, i) => ({ label: `L${i}`, value: 'v' })) }).details)
  assert.deepEqual(changedFields(form, { ...form, details: [] }), {})              // same contents, new array
  assert.deepEqual(changedFields(form, { ...form, details: [{ label: 'A', value: 'B' }] }), { details: [{ label: 'A', value: 'B' }] })
})

test('contact details: shown only when filled in; email links name the booking', () => {
  assert.equal(hasContact(null), false)
  assert.equal(hasContact({ email: '', phone: '', hours: '', note: '' }), false)
  assert.equal(hasContact({ email: '', phone: '', hours: 'Mon-Fri', note: '' }), true)
  assert.equal(mailtoLink({ email: '', phone: '1', hours: '', note: '' }, 'x'), '')
  assert.equal(mailtoLink({ email: 'lab@uni.edu', phone: '', hours: '', note: '' }, 'Booking 1 & 2', 'Ref: b1'),
    'mailto:lab@uni.edu?subject=Booking%201%20%26%202&body=Ref%3A%20b1')
})

test('induction guidance and Lab setup edits', () => {
  assert.deepEqual(guideItems({ id: 'r', name: 'n', description: '', prerequisite_ids: [], how_to_complete: ' Session ', reviewer: '', contact: 'Ann' }),
    [{ label: 'How to complete it', text: 'Session' }, { label: 'Who to ask', text: 'Ann' }])
  const before = { ...emptyRequirement(), name: 'Laser' }
  assert.deepEqual(requirementChanges(before, { ...before, reviewer: 'Lab' }), { reviewer: 'Lab' })
})

test('Today page: cards and attendance labels', () => {
  const data = { role: 'ADMIN', pending_inductions: 2, pending_bookings: 3, urgent_requests: 1, waitlisted: 0, changes_waiting: 0,
    due_soon: [booking()], due_soon_hours: 6, unfreeze_requests: 0, out_of_service: [], today: [], today_count: 0, missed_today: 0,
    can_decide_urgent: false }
  const cards = Object.fromEntries(todoCards(data).map((card) => [card.key, card]))
  assert.equal(cards.urgent.tone, 'red')
  assert.equal(cards.urgent.hint, 'A Manager decides these')
  assert.equal(cards.bookings.tone, 'red')        // some are close to their deadline
  assert.equal(cards.inductions.tone, 'amber')
  assert.equal(cards.unfreeze.tone, 'grey')
  assert.equal(attendanceLabel(booking({ attendance: 'NO_SHOW' }), NOW), 'Missed')
  assert.equal(attendanceLabel(booking(), NOW), 'Not started')
  assert.equal(attendanceLabel(booking({ start: '2030-01-01T00:00:00Z' }), NOW), 'Not checked in yet')
})
