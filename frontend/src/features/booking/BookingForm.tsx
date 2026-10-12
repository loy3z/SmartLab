import { useRef, useState } from 'react'
import { useFeedback } from '../../ui/feedback-context'
import { createBooking } from './api'
import { errorMessage, fmtDuration, newIdempotencyKey, submittedMessage } from './format'
import { SlotPicker, type SlotRange } from './SlotPicker'
import type { Resource } from './types'

export function BookingForm({ resource, onBooked }: { resource: Resource; onBooked: () => void }) {
  const feedback = useFeedback()
  const [range, setRange] = useState<SlotRange | null>(null)
  const [purpose, setPurpose] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [canRequest, setCanRequest] = useState(true)
  // One key per logical request: reused on retry, regenerated when inputs change.
  const keyRef = useRef(newIdempotencyKey())

  const pick = (r: SlotRange | null) => {
    setRange(r)
    setError('')
    keyRef.current = newIdempotencyKey()
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!range || busy || !canRequest) return
    setBusy(true)
    setError('')
    try {
      const b = await createBooking(
        { resource_id: resource.id, start: range.start, end: range.end, purpose: purpose.trim() },
        keyRef.current,
      )
      keyRef.current = newIdempotencyKey()
      const { title, message } = submittedMessage(b)
      feedback.success(message, title)
      onBooked()
    } catch (err) {
      const text = errorMessage(err)
      setError(text)
      feedback.error(text, 'Request not submitted')
      setRefreshKey((n) => n + 1)
    } finally {
      setBusy(false)
    }
  }

  const minutes = range ? (Date.parse(range.end) - Date.parse(range.start)) / 60000 : 0

  return (
    <form onSubmit={submit} className="bk-form">
      <h2>{resource.name}</h2>
      <p className="bk-muted">
        {resource.location} · open {resource.opening_time.slice(0, 5)}–{resource.closing_time.slice(0, 5)} · up to {fmtDuration(resource.max_booking_minutes)}
      </p>
      <SlotPicker resource={resource} onSelect={pick} refreshKey={refreshKey} onEligibility={setCanRequest} />
      <label className="bk-block">
        Purpose
        <textarea
          value={purpose}
          maxLength={1000}
          required
          placeholder="What will you use it for? e.g. Thesis experiment, group project build"
          onChange={(e) => setPurpose(e.target.value)}
          rows={3}
        />
      </label>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button className="bk-btn-yellow" type="submit" disabled={!range || busy || !purpose.trim() || !canRequest}>
          {busy ? 'Submitting…' : range ? `Request ${fmtDuration(minutes)}` : 'Request booking'}
        </button>
        {canRequest && (
          <span className="bk-muted">An admin reviews every request. If nobody decides within the review period, the system decides automatically.</span>
        )}
      </div>
      {error && <p className="bk-error" role="alert">{error}</p>}
    </form>
  )
}
