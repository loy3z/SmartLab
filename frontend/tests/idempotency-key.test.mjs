import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

import { newIdempotencyKey } from '../src/features/booking/format.ts'

const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, 'crypto')

afterEach(() => {
  if (originalCrypto) Object.defineProperty(globalThis, 'crypto', originalCrypto)
  else delete globalThis.crypto
})

test('uses randomUUID when the browser provides it', () => {
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: { randomUUID: () => 'fixed-uuid' },
  })

  assert.equal(newIdempotencyKey(), 'bk-fixed-uuid')
})

test('works on an HTTP origin where randomUUID is unavailable', () => {
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: {
      getRandomValues(values) {
        values.set([1, 2, 3, 4])
        return values
      },
    },
  })

  assert.match(newIdempotencyKey(), /^bk-[a-z0-9]+-00000001000000020000000300000004$/)
})
