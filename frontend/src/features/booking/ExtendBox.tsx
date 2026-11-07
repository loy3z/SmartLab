// 1.24.0 (client, Week 8): finish a booking in progress later, when nobody has booked the time after.
import { useState } from 'react'
import { extendBooking } from '../../api/index.ts'
import { errorMessage, fmtDuration, fmtTime, minutesBetween } from './format'
import { extendOptions } from './extend'
import type { Booking, Resource } from '../../api/types/index.ts'

export function ExtendBox({ booking, resource, isManager, onDone, onClose }: {
  booking: Booking
  resource: Resource
  isManager: boolean
  onDone: (updated: Booking) => void
  onClose: () => void
}) {
  // A Manager overrides the normal 3-hour limit; the resource's own longest booking still applies.
  const maximum = isManager ? resource.max_booking_minutes : resource.effective_max_booking_minutes ?? resource.max_booking_minutes
  const options = extendOptions(booking, resource, maximum)
  const [end, setEnd] = useState(options[0] ?? '')
  const [busy, setBusy] = useState(false)
  // Shown here, not as a toast: in the Manager page this box sits in a Modal that hides toasts.
  const [error, setError] = useState('')
  const askManager = isManager ? '' : ' If the rules do not allow it, contact a Manager.'

  async function save() {
    setBusy(true)
    setError('')
    try {
      onDone(await extendBooking(booking.id, end))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bk-resched">
      {options.length === 0 ? (
        <p className="bk-muted">This booking already ends at closing time or at its longest length.{askManager}</p>
      ) : <>
        <label className="bk-block">
          <span>New end time</span>
          <select value={end} onChange={(e) => { setEnd(e.target.value); setError('') }}>
            {options.map((value) => (
              <option key={value} value={value}>{fmtTime(value)} (+{fmtDuration(minutesBetween(booking.end, value))})</option>
            ))}
          </select>
        </label>
        <p className="bk-muted">Applies at once if nobody has booked the time after.{askManager}</p>
      </>}
      {error && <p className="bk-error" role="alert">Not extended: {error}</p>}
      <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
        {options.length > 0 && (
          <button className="ui-btn ui-btn-primary ui-btn-sm" disabled={!end || busy} onClick={() => void save()}>
            {busy ? 'Saving…' : 'Extend booking'}
          </button>
        )}
        <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose}>Close</button>
      </div>
    </div>
  )
}
