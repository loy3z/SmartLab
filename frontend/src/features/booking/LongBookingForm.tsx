import { useRef, useState } from 'react'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { lookupPerson, requestLongBooking } from '../../api/index.ts'
import { errorMessage, fmtDuration, fmtRange, newIdempotencyKey, submittedMessage } from './format'
import { SlotPicker, type SlotRange } from './SlotPicker'
import type { PersonBrief, Resource } from '../../api/types/index.ts'

export function LongBookingForm({ resource, onBooked }: { resource: Resource; onBooked: () => void }) {
  const { user } = useAuth()
  const feedback = useFeedback()
  const isStaff = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const [forOther, setForOther] = useState(false)
  const [zid, setZid] = useState('')
  const [person, setPerson] = useState<PersonBrief | null>(null)
  const [range, setRange] = useState<SlotRange | null>(null)
  const [purpose, setPurpose] = useState('')
  const [reason, setReason] = useState('')
  const [canRequest, setCanRequest] = useState(false)
  const [checking, setChecking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const normalMaximum = resource.effective_max_booking_minutes ?? resource.max_booking_minutes
  const step = resource.selection_step_minutes ?? resource.slot_minutes
  const [limits, setLimits] = useState({ minimum: (Math.floor(normalMaximum / step) + 1) * step, maximum: Math.floor(resource.max_booking_minutes / step) * step })
  const requestKey = useRef(newIdempotencyKey())
  const lookupGeneration = useRef(0)
  const ready = !forOther || Boolean(person)
  const supported = limits.minimum <= limits.maximum
  const minutes = range ? (Date.parse(range.end) - Date.parse(range.start)) / 60000 : 0

  function changed() {
    requestKey.current = newIdempotencyKey()
    setError('')
  }
  function invalidatePerson() {
    lookupGeneration.current += 1
    setPerson(null)
    setChecking(false)
    setRange(null)
    setCanRequest(false)
    changed()
  }
  async function checkPerson() {
    const value = zid.trim().toLowerCase()
    if (!/^z\d{7}$/.test(value)) return setError('zID must be z followed by 7 digits, e.g. z5123456.')
    const generation = ++lookupGeneration.current
    setChecking(true)
    try {
      const found = await lookupPerson(value)
      if (generation !== lookupGeneration.current) return
      setPerson(found)
      setRange(null)
      changed()
    } catch (e) {
      if (generation !== lookupGeneration.current) return
      setPerson(null)
      setError(errorMessage(e))
    } finally {
      if (generation === lookupGeneration.current) setChecking(false)
    }
  }
  const complete = ready && supported && canRequest && range && minutes >= limits.minimum && minutes <= limits.maximum && purpose.trim() && reason.trim()
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!complete || !range || busy) return
    setBusy(true)
    setError('')
    try {
      const booking = await requestLongBooking({ resource_id: resource.id, start: range.start, end: range.end,
        purpose: purpose.trim(), long_booking_reason: reason.trim(), ...(forOther && person ? { on_behalf_of_zid: person.zid } : {}) }, requestKey.current)
      const result = submittedMessage(booking)
      feedback.success(result.message, result.title)
      onBooked()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return <form className="bk-form" onSubmit={submit}>
    <h2>Request a longer booking: {resource.name}</h2>
    <p className="bk-muted">Normal sessions are limited to {fmtDuration(normalMaximum)}. {supported
      ? `Request from ${fmtDuration(limits.minimum)} to ${fmtDuration(limits.maximum)} for a single session.`
      : 'This resource cannot accommodate a longer session.'} The weekly allowance, future-booking limit and booking window still apply.</p>
    <div className="ui-callout is-blue" role="status"><div><strong>A Manager must approve a longer booking</strong>
      <p>A free time is held during review. Conflicting requests join the waitlist in submission order. This request is never approved automatically and expires if no Manager decides before its review deadline.</p>
    </div></div>
    {isStaff && <fieldset className="bk-for"><legend>Book for</legend>
      <label><input type="radio" name="long-booking-for" checked={!forOther} onChange={() => { setForOther(false); invalidatePerson() }} /> Myself</label>
      <label><input type="radio" name="long-booking-for" checked={forOther} onChange={() => { setForOther(true); invalidatePerson() }} /> Someone else</label>
      {forOther && <div className="bk-for-person">
        <input aria-label="zID of the person to book for" maxLength={8} placeholder="e.g. z5123456" value={zid} onChange={event => { setZid(event.target.value); invalidatePerson() }} />
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={checking} onClick={() => void checkPerson()}>{checking ? 'Checking…' : 'Check zID'}</button>
        {person && <span role="status">Requesting for {person.display_name} ({person.zid})</span>}
      </div>}
    </fieldset>}
    {ready && supported ? <SlotPicker key={forOther ? person?.zid : 'self'} resource={resource} longBooking forZid={forOther ? person?.zid : undefined}
      onSelect={value => { setRange(value); if (value) changed() }} onEligibility={setCanRequest}
      onAvailability={data => setLimits(current => ({ minimum: data.min_booking_minutes ?? current.minimum, maximum: data.max_booking_minutes ?? current.maximum }))}
      takenNote="This request joins the waitlist in submission order. If the time frees up, a Manager must approve the longer session before its review deadline." />
      : !ready && <p className="ui-hint">Check the person's zID to choose a time.</p>}
    <label className="bk-block"><span>Purpose <span className="bk-required">Required</span></span>
      <textarea required rows={2} maxLength={1000} value={purpose} onChange={event => { setPurpose(event.target.value); changed() }} />
    </label>
    <label className="bk-block"><span>Why a longer session is needed <span className="bk-required">Required</span></span>
      <textarea required rows={3} maxLength={1000} value={reason} onChange={event => { setReason(event.target.value); changed() }} />
    </label>
    <div className="bk-submit-row">
      {range && <span className="bk-submit-time">{fmtRange(range.start, range.end)}</span>}
      <button type="submit" className="bk-btn-yellow" disabled={busy || !complete}>{busy ? 'Submitting…' : 'Submit long-booking request'}</button>
      {error && <span className="bk-error" role="alert">Request not submitted: {error}</span>}
    </div>
  </form>
}
