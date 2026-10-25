import { useRef, useState } from 'react'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { createBooking, lookupPerson } from './api'
import { errorMessage, fmtDuration, fmtRange, newIdempotencyKey, SEPARATE_BOOKING_TEXT, submitBlocker, submittedMessage } from './format'
import { ResourceFacts } from './ResourceCard' // Sprint 3 (1.16.0)
import { SlotPicker, type SlotRange } from './SlotPicker'
import type { PersonBrief, Resource } from './types'

type BookFor = 'self' | 'other'

export function BookingForm({ resource, onBooked, initialDate, initialStart, initialMinutes }: {
  resource: Resource
  onBooked: () => void
  /** From the day grid: open on this day with this period already selected. */
  initialDate?: string
  initialStart?: string
  initialMinutes?: number
}) {
  const feedback = useFeedback()
  const { user } = useAuth()
  const isStaff = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const [range, setRange] = useState<SlotRange | null>(null)
  const [purpose, setPurpose] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [canRequest, setCanRequest] = useState(true)
  // Admin/Manager: book for themselves or on behalf of someone (checked by zID first).
  const [bookFor, setBookFor] = useState<BookFor>('self')
  const [zidInput, setZidInput] = useState('')
  const [person, setPerson] = useState<PersonBrief | null>(null)
  const [lookupError, setLookupError] = useState('')
  const [checking, setChecking] = useState(false)
  // Urgent request: sooner than the normal booking window; a Manager must approve it.
  const [urgent, setUrgent] = useState(false)
  const [urgentReason, setUrgentReason] = useState('')
  const bookingPurpose = urgent ? urgentReason.trim() : purpose.trim()
  const testBypass = Boolean(user?.bypass_booking_rules && bookFor === 'self')
  // One key per logical request: reused on retry, regenerated when inputs change.
  const keyRef = useRef(newIdempotencyKey())

  const pick = (r: SlotRange | null) => {
    setRange(r)
    setError('')
    keyRef.current = newIdempotencyKey()
  }

  function chooseBookFor(next: BookFor) {
    setBookFor(next)
    setPerson(null)
    setLookupError('')
    pick(null)
  }

  async function checkPerson() {
    const zid = zidInput.trim().toLowerCase()
    if (!/^z\d{7}$/.test(zid)) return setLookupError('zID must be z followed by 7 digits, e.g. z5123456.')
    setChecking(true)
    setLookupError('')
    try {
      setPerson(await lookupPerson(zid))
      pick(null)
    } catch (err) {
      setPerson(null)
      setLookupError(errorMessage(err))
    } finally {
      setChecking(false)
    }
  }

  const forZid = bookFor === 'other' ? person?.zid : undefined
  const ready = bookFor === 'self' || Boolean(person)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!range || busy || !canRequest || !ready) return
    if (urgent && !urgentReason.trim()) return setError('Explain why the request is urgent.')
    setBusy(true)
    setError('')
    try {
      const b = await createBooking(
        {
          resource_id: resource.id, start: range.start, end: range.end, purpose: bookingPurpose,
          ...(forZid ? { on_behalf_of_zid: forZid } : {}),
          ...(urgent ? { urgent: true, urgent_reason: urgentReason.trim() } : {}),
        },
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
  // Sprint 3 (1.16.0): why the submit button is disabled, in the order the form is filled in.
  const missing = busy ? '' : submitBlocker({ ready, canRequest, hasTime: Boolean(range), hasPurpose: urgent || Boolean(purpose.trim()),
    needsReason: urgent && !urgentReason.trim() })

  return (
    <form onSubmit={submit} className="bk-form">
      <h2>{resource.name}</h2>
      <p className="bk-muted">
        {resource.location} · {testBypass ? 'test booking: any future time, up to 24 h' : `open ${resource.opening_time.slice(0, 5)}–${resource.closing_time.slice(0, 5)} · up to ${fmtDuration(resource.max_booking_minutes)}`}
      </p>
      {/* Sprint 3 (1.16.0): everything the Manager wrote about it, and what the booking does not include. */}
      {resource.description && <p className="bk-muted">{resource.description}</p>}
      <ResourceFacts resource={resource} />
      <p className="bk-muted bk-separate">{SEPARATE_BOOKING_TEXT[resource.kind]}</p>

      {isStaff && (
        <fieldset className="bk-for">
          <legend>Book for</legend>
          <label><input type="radio" name="book-for" checked={bookFor === 'self'} onChange={() => chooseBookFor('self')} /> Myself</label>
          <label><input type="radio" name="book-for" checked={bookFor === 'other'} onChange={() => chooseBookFor('other')} /> Someone else</label>
          {bookFor === 'other' && (
            <div className="bk-for-person">
              <input aria-label="zID of the person to book for" placeholder="e.g. z5123456" maxLength={8} value={zidInput}
                onChange={(e) => { setZidInput(e.target.value); setPerson(null); setLookupError(''); pick(null) }}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void checkPerson() } }} />
              <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={checking} onClick={() => void checkPerson()}>
                {checking ? 'Checking…' : 'Check zID'}
              </button>
              {person && <span className="bk-for-found" role="status">Booking for <b>{person.display_name}</b> ({person.zid})</span>}
              {lookupError && <span className="bk-error" role="alert">{lookupError}</span>}
            </div>
          )}
          <small className="bk-muted">The booking belongs to that person and their induction is checked. You are recorded as the creator.</small>
        </fieldset>
      )}

      <label className="bk-urgent">
        <input type="checkbox" checked={urgent} onChange={(e) => { setUrgent(e.target.checked); pick(null) }} />
        Urgent request (sooner than the normal booking window)
      </label>
      {urgent && (
        <label className="bk-block">
          <span>Purpose and urgency <span className="bk-required">Required</span></span>
          <textarea value={urgentReason} maxLength={500} rows={2} required
            placeholder="Briefly describe what you’ll use it for and why it cannot wait."
            onChange={(e) => setUrgentReason(e.target.value)} />
          <small className="bk-muted">{testBypass ? 'Test overrides are on. Free times are approved immediately.' : 'Only a Manager can approve an urgent request; it is never approved automatically. Induction and conflict rules still apply.'}</small>
        </label>
      )}

      {ready ? (
        <SlotPicker resource={resource} onSelect={pick} refreshKey={refreshKey} onEligibility={setCanRequest}
          forZid={forZid} urgent={urgent} initialDate={initialDate} initialStart={initialStart} initialMinutes={initialMinutes}
          /* Sprint 3 (1.16.0): route someone who wants an earlier day to the urgent request */
          onAskEarlier={() => { setUrgent(true); pick(null) }} />
      ) : (
        <div className="ui-hint">Enter the person's zID and check it to see their availability.</div>
      )}
      {!urgent && <label className="bk-block">
        <span>Purpose <span className="bk-required">Required</span></span>{/* Sprint 3 (1.16.0) */}
        <textarea
          value={purpose}
          maxLength={1000}
          required
          placeholder="What will you use it for? e.g. Thesis experiment, group project build"
          onChange={(e) => setPurpose(e.target.value)}
          rows={3}
        />
      </label>}
      {/* Sprint 3 (1.16.0): bk-submit-row stays at the bottom of the dialog on phones, with the chosen time. */}
      <div className="bk-submit-row">
        {range && <span className="bk-submit-time">{fmtRange(range.start, range.end)}</span>}
        <button className="bk-btn-yellow" type="submit"
          disabled={!range || busy || !bookingPurpose || !canRequest || !ready}>
          {busy ? 'Submitting…' : range ? `${testBypass ? 'Book' : 'Request'} ${fmtDuration(minutes)}${urgent ? ' (urgent)' : ''}` : 'Request booking'}
        </button>
        {/* Sprint 3 (1.16.0): say what is still missing instead of leaving a grey button to guess at. */}
        {missing ? <span className="bk-missing" role="status">{missing}</span> : canRequest && !urgent && (
          <span className="bk-muted">{testBypass ? 'Test booking: approved immediately. Existing bookings cannot be displaced.' : 'An admin reviews every request. If nobody decides within the review period, the system decides automatically.'}</span>
        )}
      </div>
      {error && <p className="bk-error" role="alert">{error}</p>}
    </form>
  )
}
