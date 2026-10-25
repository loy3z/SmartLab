// Sprint 3: form rules of the Manager's resource setup page.
import assert from 'node:assert/strict'
import test from 'node:test'
import { changedFields, checkResource, emptyResource, resourceToInput, toMinutes } from '../src/features/manager/resource-form.ts'

const form = (overrides = {}) => ({ ...emptyResource('req-1'), name: 'Microscope 900', location: 'Lab Room 1', ...overrides })

test('a filled-in form has no problems', () => {
  assert.deepEqual(checkResource('EQUIPMENT', form()), {})
  assert.equal(toMinutes('08:30:00'), 510)
})

test('required fields and room rules', () => {
  const problems = checkResource('ROOM', form({ name: ' ', location: '', required_qualification_id: '', category: 'Optics' }))
  assert.deepEqual(Object.keys(problems).sort(), ['location', 'name', 'required_qualification_id', 'room_id'])
})

test('time rules match the backend', () => {
  assert.ok(checkResource('ROOM', form({ slot_minutes: 20 })).slot_minutes)
  assert.ok(checkResource('ROOM', form({ opening_time: '18:00', closing_time: '09:00' })).closing_time)
  assert.ok(checkResource('ROOM', form({ opening_time: '08:15' })).opening_time)
  assert.ok(checkResource('ROOM', form({ max_booking_minutes: 45 })).max_booking_minutes)
  assert.ok(checkResource('ROOM', form({ opening_time: '09:00', closing_time: '11:00', max_booking_minutes: 180 })).max_booking_minutes)
  assert.ok(checkResource('ROOM', form({ pending_hold_minutes: 0 })).pending_hold_minutes)
  assert.deepEqual(checkResource('ROOM', form({ slot_minutes: 15, opening_time: '08:15', max_booking_minutes: 45 })), {})
})

test('an edit sends only the changed fields', () => {
  const before = resourceToInput({ id: 'r', name: 'Lab', kind: 'ROOM', location: 'A', description: '', active: true,
    required_qualification_id: 'req-1', slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00:00',
    closing_time: '20:00:00', timezone: 'Australia/Sydney', pending_hold_minutes: 1440, status: 'AVAILABLE',
    status_reason: null, room_id: null, category: null })
  assert.equal(before.opening_time, '08:00')
  assert.deepEqual(changedFields(before, { ...before, closing_time: '17:00', description: 'Shorter' }),
    { closing_time: '17:00', description: 'Shorter' })
  assert.deepEqual(changedFields(before, before), {})
})
