// Sprint 3 (1.15.0): helpers behind the visual pass (notification bell, resource covers, time grid).
import assert from 'node:assert/strict'
import test from 'node:test'
import { groupNotifications, notificationIcon, shouldRing } from '../src/features/notifications/notifications.ts'
import { coverKey } from '../src/features/booking/covers.ts'
import { nowLineFraction } from '../src/features/booking/slot-cells.ts'

test('notification icons: reminders get a clock, otherwise the tone decides', () => {
  assert.equal(notificationIcon('BOOKING_REMINDER'), 'clock')
  assert.equal(notificationIcon('INDUCTION_EXPIRING'), 'clock')
  assert.equal(notificationIcon('BOOKING_APPROVED'), 'check')
  assert.equal(notificationIcon('BOOKING_REJECTED'), 'cross')
  assert.equal(notificationIcon('UNFREEZE_REJECTED'), 'cross')
  assert.equal(notificationIcon('BOOKING_SUBMITTED'), 'info')
})

test('notifications are grouped by Sydney day: Today first, then Earlier, empty groups left out', () => {
  // 2030-01-10 09:00 in Sydney (UTC+11) is 2030-01-09T22:00Z.
  const now = Date.parse('2030-01-09T22:00:00Z')
  const items = [
    { id: 'a', created_at: '2030-01-09T21:30:00Z' }, // 08:30 Sydney, same day
    { id: 'b', created_at: '2030-01-09T13:30:00Z' }, // 00:30 Sydney, same day although UTC says the 9th
    { id: 'c', created_at: '2030-01-09T12:30:00Z' }, // 23:30 Sydney on the 9th
  ]
  const groups = groupNotifications(items, now)
  assert.deepEqual(groups.map((group) => [group.label, group.items.map((item) => item.id)]), [['Today', ['a', 'b']], ['Earlier', ['c']]])
  assert.deepEqual(groupNotifications([], now), [])
  assert.deepEqual(groupNotifications([items[2]], now).map((group) => group.label), ['Earlier'])
})

test('the bell rings only when the unread count goes up after the first load', () => {
  assert.equal(shouldRing(null, 3), false) // opening the site
  assert.equal(shouldRing(2, 3), true)
  assert.equal(shouldRing(3, 3), false)
  assert.equal(shouldRing(3, 1), false) // read some
})

test('resource covers: rooms, demo categories, Manager-typed categories, then the name, then a default', () => {
  assert.equal(coverKey({ kind: 'ROOM', name: 'Lab Room 1', category: null }), 'room')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Microscope 001', category: 'Microscopy' }), 'microscopy')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Thermal Camera 001', category: 'Imaging' }), 'imaging')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Oscilloscope 001', category: 'Electronics testing' }), 'electronics')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Fume Extractor 001', category: 'Soldering' }), 'soldering')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: '3D Printer 001', category: 'Fabrication' }), 'fabrication')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Centrifuge 001', category: 'Lab analysis' }), 'analysis')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Bench', category: '3D printing' }), 'fabrication')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Laser Cutter 002', category: null }), 'fabrication')
  assert.equal(coverKey({ kind: 'EQUIPMENT', name: 'Glove box', category: 'Safety' }), 'equipment')
})

test('now line: position across the shown cells, none outside them', () => {
  const slots = [
    { start: '2030-01-10T08:00:00+11:00', end: '2030-01-10T08:30:00+11:00' },
    { start: '2030-01-10T08:30:00+11:00', end: '2030-01-10T09:00:00+11:00' },
  ]
  assert.equal(nowLineFraction(slots, Date.parse('2030-01-10T08:15:00+11:00')), 0.25)
  assert.equal(nowLineFraction(slots, Date.parse('2030-01-10T08:45:00+11:00')), 0.75)
  assert.equal(nowLineFraction(slots, Date.parse('2030-01-10T07:59:00+11:00')), null) // before opening
  assert.equal(nowLineFraction(slots, Date.parse('2030-01-10T09:00:00+11:00')), null) // after the last cell
  assert.equal(nowLineFraction(slots, Date.parse('2030-01-11T08:15:00+11:00')), null) // another day
  assert.equal(nowLineFraction([], Date.now()), null)
})
