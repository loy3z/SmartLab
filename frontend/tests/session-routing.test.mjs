import assert from 'node:assert/strict'
import test from 'node:test'
import { canAccess, homePath, isKnownPath, loginDestination, normalizePath } from '../src/app/routes.ts'

// Admins are tutor-like students nominated by a Manager: they keep booking and induction pages.
const bookingPaths = ['/resources', '/bookings', '/induction']
const staffPaths = ['/admin/qualifications', '/admin/bookings']
const sharedPaths = ['/account', '/help']
const roles = ['STUDENT', 'ADMIN', 'MANAGER']

test('each role lands on a page it can actually access', () => {
  assert.equal(homePath('STUDENT'), '/dashboard')
  assert.equal(homePath('ADMIN'), '/admin/qualifications')
  assert.equal(homePath('MANAGER'), '/manager/bookings')
  for (const role of roles) {
    assert.equal(canAccess(homePath(role), role), true)
  }
})

test('students and admins can book; managers and the student dashboard stay separate', () => {
  for (const path of bookingPaths) {
    assert.equal(isKnownPath(path), true, path)
    assert.equal(canAccess(path, 'STUDENT'), true, path)
    assert.equal(canAccess(path, 'ADMIN'), true, path)
    assert.equal(canAccess(path, 'MANAGER'), false, path)
  }
  assert.equal(canAccess('/dashboard', 'STUDENT'), true)
  assert.equal(canAccess('/dashboard', 'ADMIN'), false)
  assert.equal(canAccess('/dashboard', 'MANAGER'), false)
})

test('review pages allow Admin and Manager, while management is Manager-only', () => {
  for (const path of staffPaths) {
    assert.equal(isKnownPath(path), true, path)
    assert.equal(canAccess(path, 'STUDENT'), false, path)
    assert.equal(canAccess(path, 'ADMIN'), true, path)
    assert.equal(canAccess(path, 'MANAGER'), true, path)
  }
  for (const path of ['/manager/bookings', '/manager/users']) {
    assert.equal(isKnownPath(path), true, path)
    assert.equal(canAccess(path, 'STUDENT'), false, path)
    assert.equal(canAccess(path, 'ADMIN'), false, path)
    assert.equal(canAccess(path, 'MANAGER'), true, path)
  }
})

test('all signed-in roles can read their account and help', () => {
  for (const path of sharedPaths) {
    assert.equal(isKnownPath(path), true, path)
    for (const role of roles) assert.equal(canAccess(path, role), true, `${role}: ${path}`)
  }
})

test('unknown and partial paths are denied rather than matching a permitted prefix', () => {
  for (const path of ['/missing', '/admin', '/admin/qualifications/extra', '/account/../admin/bookings', '__proto__', 'constructor', 'toString']) {
    assert.equal(isKnownPath(path), false, path)
    for (const role of roles) assert.equal(canAccess(path, role), false, `${role}: ${path}`)
  }
})

test('router pathnames preserve the existing trailing slash policy', () => {
  assert.equal(normalizePath(''), '/')
  assert.equal(normalizePath('/'), '/')
  assert.equal(normalizePath('/resources'), '/resources')
  assert.equal(normalizePath('/resources/'), '/resources')
  assert.equal(isKnownPath(normalizePath('/does-not-exist/')), false)
  assert.equal(isKnownPath(normalizePath('/Resources')), false)
})

test('login returns to an authorized deep link with its query intact', () => {
  assert.equal(loginDestination({ from: '/bookings' }, 'STUDENT'), '/bookings')
  assert.equal(loginDestination({ from: '/resources/?kind=ROOM' }, 'STUDENT'), '/resources/?kind=ROOM')
  assert.equal(loginDestination({ from: '/admin/bookings?status=WAITLISTED' }, 'MANAGER'), '/admin/bookings?status=WAITLISTED')
  assert.equal(loginDestination({ from: '/manager/users' }, 'MANAGER'), '/manager/users')
})

test('login rejects forbidden, unknown, external and malformed return destinations', () => {
  for (const from of ['/admin/bookings', '/missing', '/Resources', '/login', '//example.com', 'https://example.com', '/account/../admin/bookings', 42, null]) {
    assert.equal(loginDestination({ from }, 'STUDENT'), '/dashboard')
  }
  for (const state of [null, undefined, {}, 'invalid', { from: '/dashboard' }]) {
    assert.equal(loginDestination(state, 'ADMIN'), '/admin/qualifications')
  }
  assert.equal(loginDestination({ from: '/resources' }, 'ADMIN'), '/resources')
  assert.equal(loginDestination({ from: '/resources' }, 'MANAGER'), '/manager/bookings')
})
