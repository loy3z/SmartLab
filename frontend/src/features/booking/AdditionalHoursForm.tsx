import { useRef, useState } from 'react'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { lookupPerson, requestAdditionalHours } from '../../api/index.ts'
import { errorMessage, fmtDuration, fmtRange, newIdempotencyKey, submittedMessage } from './format'
import { SlotPicker, type SlotRange } from './SlotPicker'
import type { PersonBrief, Resource } from '../../api/types/index.ts'

export function AdditionalHoursForm({ resource, onBooked }: { resource: Resource; onBooked: () => void }) {
  const { user } = useAuth()
  const feedback = useFeedback()
  const isStaff = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const [forOther, setForOther] = useState(false)
  const [zid, setZid] = useState('')
  const [person, setPerson] = useState<PersonBrief | null>(null)
  const [range, setRange] = useState<SlotRange | null>(null)
  const [purpose, setPurpose] = useState('')
  const [reason, setReason] = useState('')
  const [collecting, setCollecting] = useState(false)
  const [collectionReason, setCollectionReason] = useState('')
  const [windowHours, setWindowHours] = useState<number | null>(null)
  const [canRequest, setCanRequest] = useState(false)
  const [checking, setChecking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const requestKey = useRef(newIdempotencyKey())
  const lookupGeneration = useRef(0)
  const ready = !forOther || Boolean(person)
  const maximum = resource.effective_max_booking_minutes ?? resource.max_booking_minutes

  function changed() {
    requestKey.current = newIdempotencyKey()
    setError('')
  }
  function invalidatePersonLookup() {
    lookupGeneration.current += 1
    setPerson(null)
    setChecking(false)
  }
  function chooseRecipient(other: boolean) {
    setForOther(other)
    invalidatePersonLookup()
    setRange(null)
    setCanRequest(false)
    setWindowHours(null)
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
  const complete = ready && canRequest && range && purpose.trim() && reason.trim() && (!collecting || collectionReason.trim())
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!complete || !range || busy) return
    setBusy(true)
    setError('')
    try {
      const booking = await requestAdditionalHours({
        resource_id: resource.id, start: range.start, end: range.end, purpose: purpose.trim(),
        additional_hours_reason: reason.trim(), active_data_collection: collecting,
        ...(collecting ? { data_collection_reason: collectionReason.trim() } : {}),
        ...(forOther && person ? { on_behalf_of_zid: person.zid } : {}),
      }, requestKey.current)
      const message = submittedMessage(booking)
      feedback.success(message.message, message.title)
      onBooked()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return <form className="bk-form" onSubmit={submit}>
    <h2>Request additional hours: {resource.name}</h2>
    <p className="bk-muted">Request unused lab capacity beyond the normal weekly allowance. Each session is still limited to {fmtDuration(maximum)}; the future-booking limit and latest bookable date still apply.</p>
    <div className="ui-callout is-blue" role="status"><div>
      <strong>A Manager must approve this request</strong>
      <p>You can submit in advance.{windowHours !== null ? ` Approval opens ${windowHours} hours before the requested start.` : ' Approval opens shortly before the requested start.'} Pending requests do not reserve or hold the time and are never approved automatically. If not approved before the start, they expire.</p>
    </div></div>

    {isStaff && <fieldset className="bk-for">
      <legend>Book for</legend>
      <label><input type="radio" name="additional-for" checked={!forOther} onChange={() => chooseRecipient(false)} /> Myself</label>
      <label><input type="radio" name="additional-for" checked={forOther} onChange={() => chooseRecipient(true)} /> Someone else</label>
      {forOther && <div className="bk-for-person">
        <input aria-label="zID of the person to book for" placeholder="e.g. z5123456" maxLength={8} value={zid}
          onChange={event => { setZid(event.target.value); invalidatePersonLookup(); setRange(null); setCanRequest(false); changed() }} />
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={checking} onClick={() => void checkPerson()}>{checking ? 'Checking…' : 'Check zID'}</button>
        {person && <span role="status">Requesting for {person.display_name} ({person.zid})</span>}
      </div>}
    </fieldset>}

    {ready ? <SlotPicker key={forOther ? person?.zid : 'self'} resource={resource} additionalHours forZid={forOther ? person?.zid : undefined}
      onSelect={value => { setRange(value); if (value) changed() }} onEligibility={setCanRequest}
      onAvailability={data => setWindowHours(data.additional_hours_approval_window_hours ?? null)}
      takenNote="You can request this time, but it does not reserve a place. A Manager can approve only if capacity becomes available and this request is next in the additional-hours queue." />
      : <p className="ui-hint">Check the person's zID to choose a time.</p>}

    <label className="bk-block"><span>Purpose <span className="bk-required">Required</span></span>
      <textarea required maxLength={1000} rows={2} value={purpose} onChange={event => { setPurpose(event.target.value); changed() }} />
    </label>
    <label className="bk-block"><span>Why additional hours are needed <span className="bk-required">Required</span></span>
      <textarea required maxLength={1000} rows={3} value={reason} onChange={event => { setReason(event.target.value); changed() }} />
    </label>
    <label className="bk-urgent"><input type="checkbox" checked={collecting} onChange={event => { setCollecting(event.target.checked); changed() }} />
      {forOther ? 'This researcher is currently collecting data' : 'I am currently collecting data'}
    </label>
    {collecting && <label className="bk-block"><span>Describe the active data collection <span className="bk-required">Required</span></span>
      <textarea required maxLength={1000} rows={3} value={collectionReason} onChange={event => { setCollectionReason(event.target.value); changed() }} />
      <small className="bk-muted">A Manager must confirm this claim before approving.</small>
    </label>}
    <p className="bk-muted">Researchers with no recorded lab use in the requested week and those actively collecting data have equal priority. Within each priority group, earlier requests come first. Approval also depends on spare capacity.</p>
    <div className="bk-submit-row">
      {range && <span className="bk-submit-time">{fmtRange(range.start, range.end)}</span>}
      <button type="submit" className="bk-btn-yellow" disabled={busy || !complete}>{busy ? 'Submitting…' : 'Submit additional-hours request'}</button>
      {error && <span className="bk-error" role="alert">Request not submitted: {error}</span>}
    </div>
  </form>
}
