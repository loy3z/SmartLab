import { useEffect, useState } from 'react'
import {
  listAdminBookings,
  listResources,
  reviewBooking,
} from '../booking/api'
import {
  errorMessage,
  fmtDateTime,
  STATUS_TEXT,
} from '../booking/format'
import type { Booking, Resource } from '../booking/types'

type ReviewTab =
  | 'WAITING_QUALIFICATION'
  | 'WAITLISTED'
  | 'PENDING_APPROVAL'

const tabs: { key: ReviewTab; label: string }[] = [
  { key: 'WAITING_QUALIFICATION', label: 'Waiting for induction' },
  { key: 'WAITLISTED', label: 'Waitlisted' },
  { key: 'PENDING_APPROVAL', label: 'Manual review' },
]

export function BookingReviewPage() {
  const [tab, setTab] = useState<ReviewTab>('WAITLISTED')
  const [bookings, setBookings] = useState<Booking[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [reasons, setReasons] = useState<Record<string, string>>({})

  // Refresh server state; the backend decides expiry and promotion.
  useEffect(() => {
    const timer = window.setInterval(() => {
      setRefresh((n) => n + 1)
    }, 15000)

    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let active = true

    Promise.all([listAdminBookings(tab), listResources({})])
      .then(([bookingData, resourceData]) => {
        if (!active) return

        setBookings(
          [...bookingData.results].sort(
            (a, b) =>
              a.created_at.localeCompare(b.created_at) ||
              a.id.localeCompare(b.id),
          ),
        )
        setResources(resourceData.results)
        setLoadError('')
      })
      .catch((e: unknown) => {
        if (active) setLoadError(errorMessage(e))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [tab, refresh])

  function changeTab(next: ReviewTab) {
    if (next === tab) return
    setTab(next)
    setBookings([])
    setLoading(true)
    setLoadError('')
    setActionError('')
    setMessage('')
  }

  async function handleReview(
    booking: Booking,
    decision: 'APPROVED' | 'REJECTED',
  ) {
    if (busy) return

    const reason = (reasons[booking.id] ?? '').trim()
    setActionError('')
    setMessage('')

    if (decision === 'REJECTED' && !reason) {
      setActionError('Please enter a rejection reason.')
      return
    }

    // Never offer manual approval for a waitlisted request.
    if (
      decision === 'APPROVED' &&
      booking.status !== 'PENDING_APPROVAL'
    ) {
      setActionError('Only requests awaiting manual review can be approved.')
      return
    }

    setBusy(booking.id)

    try {
      await reviewBooking(booking.id, decision, reason)
      setBookings((current) =>
        current.filter((item) => item.id !== booking.id),
      )
      setMessage(
        decision === 'APPROVED'
          ? 'Booking approved.'
          : 'Booking rejected.',
      )
    } catch (e) {
      setActionError(errorMessage(e))
    } finally {
      setBusy(null)
      // Also refresh after an error: the server state may have changed.
      setRefresh((n) => n + 1)
    }
  }

  return (
    <>
      <h1>Booking Review</h1>
      <p className="bk-sub">
        Monitor temporary holds, waitlisted requests and manual reviews.
        Refreshes every 15 seconds.
      </p>

      <div className="bk-pills">
        {tabs.map((item) => (
          <button
            key={item.key}
            className={`bk-pill ${tab === item.key ? 'is-on' : ''}`}
            disabled={busy !== null}
            onClick={() => changeTab(item.key)}
          >
            {item.label}
          </button>
        ))}

        <button
          className="bk-pill"
          disabled={busy !== null}
          onClick={() => setRefresh((n) => n + 1)}
        >
          Refresh
        </button>
      </div>

      {tab === 'WAITING_QUALIFICATION' && (
        <p className="bk-muted">
          Review induction evidence in Qualification Review.
          A temporary hold does not mean the booking is approved.
        </p>
      )}

      {tab === 'WAITLISTED' && (
        <p className="bk-muted">
          Waitlisted requests cannot be manually approved.
          Eligible requests are automatically approved when the slot
          becomes available.
        </p>
      )}

      {tab === 'PENDING_APPROVAL' && (
        <p className="bk-muted">
          Approval requires verified induction and no conflicting
          booking or temporary hold. The server checks these conditions.
        </p>
      )}

      {loadError && <p className="bk-error">{loadError}</p>}
      {actionError && <p className="bk-error">{actionError}</p>}
      {message && <p role="status">{message}</p>}
      {loading && <p>Loading requests...</p>}

      {!loading && !loadError && bookings.length === 0 && (
        <p className="bk-muted">No requests in this category.</p>
      )}

      {bookings.map((booking) => {
        const resource = resources.find(
          (item) => item.id === booking.resource_id,
        )
        const canApprove = booking.status === 'PENDING_APPROVAL'
        const canReject =
          canApprove || booking.status === 'WAITLISTED'
        const disabled = busy !== null || Boolean(loadError)

        return (
          <section
            key={booking.id}
            className="bk-panel"
            style={{ marginBottom: 16 }}
          >
            <span className={`bk-chip st-${booking.status}`}>
              {STATUS_TEXT[booking.status]}
            </span>

            <h2>{resource?.name ?? booking.resource_id}</h2>
            <p><b>Student ID:</b> {booking.student_id}</p>
            <p>
              <b>Time:</b> {fmtDateTime(booking.start)}
              {' → '}
              {fmtDateTime(booking.end)}
            </p>
            <p><b>Purpose:</b> {booking.purpose}</p>
            <p><b>Submitted:</b> {fmtDateTime(booking.created_at)}</p>

            {booking.hold_until && (
              <p>
                <b>
                  {booking.status === 'WAITLISTED'
                    ? 'Previous hold deadline:'
                    : 'Hold deadline:'}
                </b>{' '}
                {fmtDateTime(booking.hold_until)}
              </p>
            )}

            {booking.reason_code && (
              <p><b>Reason code:</b> {booking.reason_code}</p>
            )}

            {booking.reason_code === 'HOLD_EXPIRED' && (
              <p className="bk-muted">
                The temporary hold expired. This request is now
                waitlisted and no longer reserves the slot.
              </p>
            )}

            {canReject && (
              <>
                <label htmlFor={`reason-${booking.id}`}>
                  Review reason (required when rejecting)
                </label>
                <textarea
                  id={`reason-${booking.id}`}
                  rows={3}
                  maxLength={2000}
                  style={{
                    display: 'block',
                    width: '100%',
                    margin: '8px 0 12px',
                  }}
                  value={reasons[booking.id] ?? ''}
                  disabled={disabled}
                  onChange={(e) =>
                    setReasons((current) => ({
                      ...current,
                      [booking.id]: e.target.value,
                    }))
                  }
                />

                <div style={{ display: 'flex', gap: 12 }}>
                  {canApprove && (
                    <button
                      className="bk-btn-yellow"
                      disabled={disabled}
                      onClick={() => handleReview(booking, 'APPROVED')}
                    >
                      Approve
                    </button>
                  )}

                  <button
                    disabled={disabled}
                    onClick={() => handleReview(booking, 'REJECTED')}
                  >
                    Reject
                  </button>

                  {busy === booking.id && <span>Saving...</span>}
                </div>
              </>
            )}
          </section>
        )
      })}
    </>
  )
}