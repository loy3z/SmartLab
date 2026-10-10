import { useEffect, useState } from 'react'
import {
  getToken,
  listAdminQualifications,
  listRequirements,
  reviewQualification,
} from '../booking/api'
import type { Qualification, Requirement } from '../booking/types'

export function QualificationReviewPage() {
  const [submissions, setSubmissions] = useState<Qualification[]>([])
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const [submissionData, requirementData] = await Promise.all([
          listAdminQualifications(),
          listRequirements(),
        ])

        if (active) {
          setSubmissions(submissionData.results)
          setRequirements(requirementData.results)
        }
      } catch (err: unknown) {
        if (active) {
          setError(
            err instanceof Error ? err.message : 'Failed to load applications.',
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    void load()

    return () => {
      active = false
    }
  }, [])

  async function handleReview(
    submission: Qualification,
    decision: 'VERIFIED' | 'REJECTED',
  ) {
    if (busy) return

    const reason = (reasons[submission.id] ?? '').trim()
    setError('')
    setSuccess('')

    if (decision === 'REJECTED' && !reason) {
      setError('Please enter a reason before rejecting the application.')
      return
    }

    setBusy(true)

    try {
      await reviewQualification(submission.id, decision, reason)

      setSubmissions((previous) =>
        previous.filter((item) => item.id !== submission.id),
      )

      setSuccess(
        decision === 'VERIFIED'
          ? 'Application verified successfully.'
          : 'Application rejected.',
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Review failed.')
    } finally {
      setBusy(false)
    }
  }

  async function downloadEvidence(submission: Qualification) {
    if (busy) return

    setError('')
    setSuccess('')
    setBusy(true)

    try {
      const token = getToken()
      const headers = new Headers()

      if (token) {
        headers.set('Authorization', `Bearer ${token}`)
      }

      const response = await fetch(
        `/api/v1/qualifications/${submission.id}/file/`,
        { headers },
      )

      if (!response.ok) {
        throw new Error(`Unable to download evidence (${response.status}).`)
      }

      const blob = await response.blob()
      const extension =
        blob.type === 'application/pdf'
          ? '.pdf'
          : blob.type === 'image/png'
            ? '.png'
            : blob.type === 'image/jpeg'
              ? '.jpg'
              : ''

      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `evidence-${submission.id}${extension}`
      document.body.appendChild(link)
      link.click()
      link.remove()

      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Download failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1>Induction qualification review</h1>
      <p>Review student evidence and verify or reject applications.</p>

      {error && <p role="alert" style={{ color: '#b42318' }}>{error}</p>}
      {success && <p role="status" style={{ color: '#067647' }}>{success}</p>}

      {loading && <p>Loading applications...</p>}

      {!loading && !error && submissions.length === 0 && (
        <p>No pending applications.</p>
      )}

      <div style={{ display: 'grid', gap: 16 }}>
        {submissions.map((submission) => {
          const requirement = requirements.find(
            (item) => item.id === submission.requirement_id,
          )

          return (
            <section
              key={submission.id}
              className="bk-bcard"
              style={{ padding: 20 }}
            >
              <span className="bk-chip is-warn">Pending review</span>

              <h2>{submission.title}</h2>

              <p>
                <strong>Training: </strong>
                {requirement?.name ?? submission.requirement_id}
              </p>

              <p>
                <strong>Student ID: </strong>
                {submission.student_id}
              </p>

              <p>
                <strong>Submitted: </strong>
                {new Date(submission.submitted_at).toLocaleString()}
              </p>

              <p style={{ whiteSpace: 'pre-wrap' }}>
                <strong>Notes: </strong>
                {submission.notes || 'No notes provided.'}
              </p>

              <button
                type="button"
                disabled={busy}
                onClick={() => void downloadEvidence(submission)}
              >
                Download evidence
              </button>

              <label
                style={{ display: 'grid', gap: 8, marginTop: 16 }}
              >
                Review reason (required when rejecting)
                <textarea
                  rows={3}
                  maxLength={2000}
                  disabled={busy}
                  value={reasons[submission.id] ?? ''}
                  onChange={(event) =>
                    setReasons((previous) => ({
                      ...previous,
                      [submission.id]: event.target.value,
                    }))
                  }
                />
              </label>

              <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
                <button
                  type="button"
                  className="bk-btn-yellow"
                  disabled={busy}
                  onClick={() => void handleReview(submission, 'VERIFIED')}
                >
                  Verify
                </button>

                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleReview(submission, 'REJECTED')}
                >
                  Reject
                </button>
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}