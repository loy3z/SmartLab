import { useRef, useState } from 'react'
import { createBooking } from './api'
import { errorMessage, fmtDateTime, newIdempotencyKey, STATUS_TEXT } from './format'
import { SlotPicker } from './SlotPicker'
import type { Booking, Resource, Slot } from './types'

export function BookingForm({ resource, onBooked }: { resource: Resource; onBooked: () => void }) {
  const [slot, setSlot] = useState<Slot | null>(null)
  const [purpose, setPurpose] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Booking | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  // One key per logical request: reused on retry, regenerated when inputs change.
  const keyRef = useRef(newIdempotencyKey())

  const pick = (s: Slot | null) => {
    setSlot(s)
    keyRef.current = newIdempotencyKey()
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!slot || busy) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const b = await createBooking(
        { resource_id: resource.id, start: slot.start, end: slot.end, purpose },
        keyRef.current,
      )
      setResult(b)
      keyRef.current = newIdempotencyKey()
      setRefreshKey((n) => n + 1)
      onBooked()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="bk-form">
      <h2>{resource.name}</h2>
      <p className="bk-muted">
        {resource.location} · {resource.opening_time.slice(0, 5)}–{resource.closing_time.slice(0, 5)} · max{' '}
        {resource.max_booking_minutes} min
      </p>
      <SlotPicker resource={resource} onSelect={pick} refreshKey={refreshKey} />
      {slot && (
        <p>
          Selected: <b>{fmtDateTime(slot.start)}</b> → {fmtDateTime(slot.end)}
        </p>
      )}
      <label className="bk-block">
        Purpose
        <textarea
          value={purpose}
          maxLength={1000}
          required
          onChange={(e) => setPurpose(e.target.value)}
          rows={3}
        />
      </label>
      <button className="bk-btn-yellow" type="submit" disabled={!slot || busy || !purpose.trim()}>
        {busy ? 'Submitting…' : 'Request booking'}
      </button>
      {error && <p className="bk-error">{error}</p>}
      {result && (
        <p className={result.status === 'APPROVED' ? 'bk-ok' : 'bk-muted'}>
          {STATUS_TEXT[result.status]}
          {result.reason_code === 'TIME_CONFLICT' && ' — conflicts with an approved booking; sent to manual review.'}
          {result.reason_code === 'TEMPORARY_HOLD_CONFLICT' &&
            ' — conflicts with a temporary hold; sent to manual review.'}
        </p>
      )}
    </form>
  )
}
