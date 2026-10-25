import test from 'node:test'
import assert from 'node:assert/strict'
import { evidenceProblem, MAX_EVIDENCE_BYTES } from '../src/features/induction/evidence.ts'

test('evidence is mandatory and an empty file is not a certificate', () => {
  assert.match(evidenceProblem(null), /Upload your training certificate/)
  assert.match(evidenceProblem({ name: 'certificate.pdf', size: 0 }), /empty/)
})
test('evidence rejects unsupported and oversized files, accepts supported files at the size limit', () => {
  assert.match(evidenceProblem({ name: 'certificate.exe', size: 1 }), /PDF, PNG or JPEG/)
  assert.match(evidenceProblem({ name: 'certificate.pdf', size: MAX_EVIDENCE_BYTES + 1 }), /5 MiB/)
  for (const name of ['certificate.PDF', 'certificate.png', 'certificate.jpg', 'certificate.jpeg']) {
    assert.equal(evidenceProblem({ name, size: MAX_EVIDENCE_BYTES }), '')
  }
})
