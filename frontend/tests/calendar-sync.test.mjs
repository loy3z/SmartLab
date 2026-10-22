import assert from 'node:assert/strict'
import test from 'node:test'
import { connectionSummary, syncErrorText, syncPill } from '../src/features/admin/calendar-sync.ts'
import { kindOf } from '../src/features/booking/slot-cells.ts'

const item = (sync = {}) => ({
  booking_id: 'b1', booking_status: 'APPROVED', start: '2030-01-10T01:00:00Z', end: '2030-01-10T02:00:00Z', urgent: false,
  resource: { id: 'r1', name: 'Lab Room 1', location: 'A' }, booked_for: { zid: 'z1000001', display_name: 'S' }, booked_by: null, invited: false,
  sync: { status: 'SYNCED', action: 'CREATE', attempts: 1, last_error: null, next_attempt_at: null, last_success_at: null, web_link: null, ...sync },
})
const status = (overrides = {}) => ({
  enabled: true, configured: true, mode: 'delegated_token', direction: 'system_to_outlook', invite_mode: 'allowlist',
  last_check: null, summary: { total: 0, synced: 0, pending: 0, failed: 0 }, items: [], ...overrides,
})

test('sync state pills', () => {
  assert.deepEqual(syncPill(item({ status: 'FAILED' })), { tone: 'red', text: 'Failed' })
  assert.equal(syncPill(item({ status: 'PENDING' })).text, 'Waiting')
  assert.equal(syncPill(item({ status: 'IN_PROGRESS' })).text, 'Syncing')
  assert.equal(syncPill(item({ action: 'UPDATE' })).text, 'Synced (updated)')
  assert.equal(syncPill(item({ action: 'DELETE' })).text, 'Removed (cancelled)')
})

test('connection summary and error texts give advice, never raw tokens', () => {
  assert.equal(connectionSummary(status({ enabled: false })).title, 'Calendar sync is off')
  assert.equal(connectionSummary(status({ configured: false })).title, 'Outlook is not set up')
  assert.equal(connectionSummary(status()).title, 'Connection not checked yet')
  const bad = connectionSummary(status({ last_check: { at: 'x', ok: false, code: 'TOKEN_EXPIRED', mode: 'm', calendar_name: null, owner: null } }))
  assert.equal(bad.tone, 'red')
  assert.match(bad.detail, /sign-in expired/)
  const ok = connectionSummary(status({ last_check: { at: 'x', ok: true, code: null, mode: 'm', calendar_name: 'Calendar', owner: 'me@example.test' } }))
  assert.equal(ok.detail, 'Writing to Calendar as me@example.test.')
  assert.equal(syncErrorText('SOMETHING_NEW'), 'Error SOMETHING_NEW.')
  assert.equal(syncErrorText(null), '')
})

test('day grid cells use the same meaning as the slot picker', () => {
  const slot = (overrides) => ({ start: 's', end: 'e', available: false, reason_code: null, hold_until: null, held_by_me: false, requested_by_me: false, ...overrides })
  assert.equal(kindOf(slot({ available: true })), 'free')
  assert.equal(kindOf(slot({ reason_code: 'BOOKED' })), 'taken')
  assert.equal(kindOf(slot({ reason_code: 'TEMPORARILY_HELD' })), 'held')
  assert.equal(kindOf(slot({ reason_code: 'TOO_SOON' })), 'closed')
  assert.equal(kindOf(slot({ available: true, requested_by_me: true })), 'mine')
})
