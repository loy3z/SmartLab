import assert from 'node:assert/strict'
import test from 'node:test'
import { canAccess, homePath, isKnownPath, normalizePath } from '../src/app/routes.ts'

const studentPaths = ['/dashboard', '/resources', '/bookings', '/induction']
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

test('student-only pages cannot expose booking forms to staff', () => {
  for (const path of studentPaths) {
    assert.equal(isKnownPath(path), true, path)
    assert.equal(canAccess(path, 'STUDENT'), true, path)
    assert.equal(canAccess(path, 'ADMIN'), false, path)
    assert.equal(canAccess(path, 'MANAGER'), false, path)
  }
})

test('review pages allow Admin and Manager, while management is Manager-only', () => {
  for (const path of staffPaths) {
    assert.equal(isKnownPath(path), true, path)
    assert.equal(canAccess(path, 'STUDENT'), false, path)
    assert.equal(canAccess(path, 'ADMIN'), true, path)
    assert.equal(canAccess(path, 'MANAGER'), true, path)
  }
  assert.equal(isKnownPath('/manager/bookings'), true)
  assert.equal(canAccess('/manager/bookings', 'STUDENT'), false)
  assert.equal(canAccess('/manager/bookings', 'ADMIN'), false)
  assert.equal(canAccess('/manager/bookings', 'MANAGER'), true)
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

test('hash deep links normalize query strings and trailing slashes', () => {
  assert.equal(normalizePath(''), '/')
  assert.equal(normalizePath('#'), '/')
  assert.equal(normalizePath('#/'), '/')
  assert.equal(normalizePath('#/resources'), '/resources')
  assert.equal(normalizePath('#/resources/'), '/resources')
  assert.equal(normalizePath('#/resources/?kind=ROOM'), '/resources')
  assert.equal(normalizePath('#/admin/bookings?status=WAITLISTED'), '/admin/bookings')
  assert.equal(isKnownPath(normalizePath('#/does-not-exist/?returnTo=/dashboard')), false)
})
