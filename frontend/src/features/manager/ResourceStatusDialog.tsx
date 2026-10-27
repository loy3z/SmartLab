// Sprint 3 (1.19.0): resource status and optional recovery estimate; errors stay in the dialog.
import { useId, useState, type FormEvent } from 'react'
import { updateResourceStatus } from '../../api/index.ts'
import { Modal } from '../booking/Modal'
import { errorMessage, fmtRange } from '../booking/format'
import type { Booking, Resource, ResourceStatus } from '../../api/types/index.ts'
import { dateTimeISO } from '../announcements/dates'

export function ResourceStatusDialog({ resource, status, affected, onClose, onSaved }: {
  resource: Resource; status: ResourceStatus; affected: Booking[]; onClose: () => void; onSaved: (resource: Resource) => void
}) {
  const fieldId = useId()
  const [reason, setReason] = useState('')
  const [expected, setExpected] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const reopening = status === 'AVAILABLE'
  const title = reopening ? `Reopen ${resource.name}?` : status === 'MAINTENANCE' ? `Put ${resource.name} under maintenance?` : `Close ${resource.name}?`
  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      const saved = await updateResourceStatus(resource.id, status, reopening ? '' : reason.trim(), reopening ? null : dateTimeISO(expected))
      onSaved(saved.resource)
    } catch (problem) { setError(errorMessage(problem)) }
    finally { setBusy(false) }
  }
  return <Modal label={title} onClose={() => { if (!busy) onClose() }}>
    <form className="announcement-editor" onSubmit={event => void save(event)}>
      <h2>{title}</h2>
      <p>{reopening ? 'New requests are allowed again. The resource status announcement will be removed.' : 'New requests and approvals stop. Existing bookings are kept. A status announcement will appear on the home pages.'}</p>
      {/* Card A (B1): one total for bookings and requests, the same people the server notifies. */}
      <p>{affected.length === 1 ? '1 upcoming booking or request affected.' : `${affected.length} upcoming bookings and requests affected.`} People with bookings or requests are notified using their notification settings.</p>
      {affected.slice(0, 5).map(booking => <p key={booking.id}>{fmtRange(booking.start, booking.end)} · {booking.student?.display_name ?? booking.student_id}</p>)}
      {!reopening && <>
        <div className="ui-field"><label htmlFor={`${fieldId}-reason`}>Reason (shown to students)</label><textarea id={`${fieldId}-reason`} required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></div>
        <div className="ui-field"><label htmlFor={`${fieldId}-expected`}>Expected back (optional)</label><input id={`${fieldId}-expected`} type="datetime-local" value={expected} onChange={event => setExpected(event.target.value)} /></div>
        <p className="announcement-time-note">Australia/Sydney time. This is an estimate; it does not reopen the resource automatically.</p>
      </>}
      {error && <p className="bk-error" role="alert">{error}</p>}
      <div className="announcement-actions"><button className="ui-btn ui-btn-primary" disabled={busy || (!reopening && !reason.trim())}>{busy ? 'Saving…' : reopening ? 'Reopen room' : status === 'MAINTENANCE' ? 'Start maintenance' : 'Close room'}</button>
        <button type="button" className="ui-btn ui-btn-ghost" disabled={busy} onClick={onClose}>Cancel</button></div>
    </form>
  </Modal>
}
