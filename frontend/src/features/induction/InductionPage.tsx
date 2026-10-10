import { useEffect, useState } from 'react'
import {
  listQualifications,
  listRequirements,
  submitQualification,
} from '../booking/api'
import type {
  Qualification,
  Requirement,
} from '../booking/types'

import type { FormEvent } from 'react'

const statusLabels = {
  NOT_SUBMITTED: 'Not submitted',
  PENDING: 'Pending review',
  VERIFIED: 'Verified',
  REJECTED: 'Rejected',
  EXPIRED: 'Expired',
}

export function InductionPage() {
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [qualifications, setQualifications] = useState<Qualification[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [requirementId, setRequirementId] = useState('')
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    let active = true

    Promise.all([
      listRequirements(),
      listQualifications(),
    ])
      .then(([requirementsData, qualificationsData]) => {
        if (!active) return

        setRequirements(requirementsData.results)
        setQualifications(qualificationsData.results)
      })
      .catch((err: unknown) => {
        if (!active) return

        setError(
          err instanceof Error
            ? err.message
            : 'Unable to load qualifications.',
        )
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return

    setUploadError('')
    setSuccess('')

    if (!requirementId || !title.trim() || !file) {
        setUploadError('Select a requirement, enter a title and choose a file.')
        return
    }

    if (file.size > 5 * 1024 * 1024) {
        setUploadError('The file must be no larger than 5 MiB.')
        return
    }

    if (!/\.(pdf|png|jpe?g)$/i.test(file.name)) {
        setUploadError('Please choose a PDF, PNG or JPEG file.')
        return
    }

    const latest = qualifications
        .filter((item) => item.requirement_id === requirementId)
        .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))[0]

    if (
        latest?.effective_status === 'VERIFIED' ||
        latest?.effective_status === 'PENDING'
    ) {
        setUploadError('This qualification is already verified or awaiting review.')
        return
    }

    const form = event.currentTarget
    setSubmitting(true)

    try {
        const submission = await submitQualification(
            requirementId,
            title.trim(),
            notes.trim(),
            file,
    )

    setQualifications((previous) => [
      submission,
      ...previous.filter((item) => item.id !== submission.id),
    ])

    setSuccess('Evidence submitted successfully. It is now awaiting review.')
    setRequirementId('')
    setTitle('')
    setNotes('')
    setFile(null)
    form.reset()
  } catch (err: unknown) {
    setUploadError(
      err instanceof Error ? err.message : 'Upload failed. Please try again.',
    )
  } finally {
    setSubmitting(false)
  }
}

  return (
    <div>
      <h1>Induction &amp; Training</h1>

      <p className="bk-sub">
        Submit your training evidence and check your qualification status.
      </p>

      <section className="bk-bcard">
        <h2>My qualifications</h2>

        {loading && <p role="status">Loading qualifications...</p>}

        {error && (
          <p className="bk-error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && requirements.length === 0 && (
          <p className="bk-muted">
            No training requirements are currently available.
          </p>
        )}

        {!loading && !error && requirements.map((requirement) => {
          const latest = qualifications
            .filter((item) => item.requirement_id === requirement.id)
            .sort((a, b) =>
              b.submitted_at.localeCompare(a.submitted_at),
            )[0]

          const status = latest?.effective_status ?? 'NOT_SUBMITTED'

          return (
            <div
              key={requirement.id}
              style={{
                borderTop: '1px solid #e5e7eb',
                padding: '16px 0',
              }}
            >
              <h3>{requirement.name}</h3>

              <p className="bk-muted">
                {requirement.description}
              </p>

              <span
                className={`bk-chip ${
                  status === 'VERIFIED' ? 'is-ok' : 'is-warn'
                }`}
              >
                {statusLabels[status]}
              </span>
            </div>
          )
        })}
      </section>

      <section className="bk-bcard">
        <h2>Submit induction evidence</h2>

        <p className="bk-muted">
            Upload a PDF, PNG or JPEG file, up to 5 MiB.
        </p>

        {success && <p role="status">{success}</p>}

        {uploadError && (
            <p className="bk-error" role="alert">
                {uploadError}
            </p>
        )}

        <form onSubmit={handleSubmit}>
            <fieldset
            disabled={loading || !!error || submitting}
            style={{
                border: 0,
                padding: 0,
                margin: 0,
                display: 'grid',
                gap: '16px',
                maxWidth: '600px',
                minWidth: 0,
            }}
            >
            <label style={{ display: 'grid', gap: '6px' }}>
                Training requirement
                <select
                required
                value={requirementId}
                onChange={(event) => setRequirementId(event.target.value)}
                >
                <option value="">Select a training requirement</option>

                {requirements.map((requirement) => {
                    const latest = qualifications
                    .filter((item) => item.requirement_id === requirement.id)
                    .sort((a, b) =>
                        b.submitted_at.localeCompare(a.submitted_at),
                    )[0]

                    const blocked =
                    latest?.effective_status === 'VERIFIED' ||
                    latest?.effective_status === 'PENDING'

                    return (
                    <option
                        key={requirement.id}
                        value={requirement.id}
                        disabled={blocked}
                    >
                        {requirement.name}
                        {blocked
                        ? ` (${statusLabels[latest.effective_status]})`
                        : ''}
                    </option>
                    )
                })}
                </select>
            </label>

            <label style={{ display: 'grid', gap: '6px' }}>
                Submission title
                <input
                required
                maxLength={160}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="e.g. Advanced laboratory training certificate"
                />
            </label>

            <label style={{ display: 'grid', gap: '6px' }}>
                Notes (optional)
                <textarea
                rows={3}
                maxLength={2000}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Additional information for the reviewer"
                />
            </label>

            <label style={{ display: 'grid', gap: '6px' }}>
                Training evidence
                <input
                type="file"
                required
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(event) =>
                    setFile(event.target.files?.[0] ?? null)
                }
                />
            </label>

            <button
                type="submit"
                className="bk-btn-yellow"
                disabled={!requirementId || !title.trim() || !file || submitting}
            >
                {submitting ? 'Submitting...' : 'Submit for review'}
            </button>
            </fieldset>
        </form>
        </section>
    </div>
  )
}