// 2026-11-10 (U2, U6): the bell's two keys never collide; the Help page lists the booking rules.
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { badgeKey, ringIconKey } from '../src/features/notifications/notifications.ts'
import { BOOKING_RULES } from '../src/app/booking-rules.ts'

test('the bell icon key and the badge key differ even when both are 1', () => {
  assert.notEqual(ringIconKey(1), badgeKey('1'))
  assert.notEqual(ringIconKey(0), ringIconKey(1))
})

test('the Help page lists each booking rule a student meets', () => {
  const text = BOOKING_RULES.join(' ')
  for (const word of ['7 to 28 days', '3 h', '12 h', 'urgent', 'additional hours', 'extend', "I'm here"]) {
    assert.match(text, new RegExp(word, 'i'), word)
  }
})

test('the Help page no longer tells students to refresh (it updates itself)', () => {
  const page = readFileSync(new URL('../src/app/UtilityPages.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(page, /Refresh the page to see the latest status/)
  assert.match(page, /Booking rules/)
})
