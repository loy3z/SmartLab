// 1.24.0 (client, Week 8): finish a booking in progress later. 2026-11-07: drag the end of the booking on a timeline
// (as in a calendar). For the person it is for, this asks a Manager; a Manager's extension applies at once.
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { extendBooking, getAvailability } from '../../api/index.ts'
import { errorMessage, fmtClock, fmtDuration, fmtTime, minutesBetween } from './format'
import { extendOptions, latestEnd, sydneyDate, timelineCells, waitingExtension } from './extend'
import type { Booking, Resource, Slot } from '../../api/types/index.ts'

export function ExtendBox({ booking, resource, isManager, onDone, onClose }: {
  booking: Booking
  resource: Resource
  isManager: boolean
  onDone: (updated: Booking) => void
  onClose: () => void
}) {
  const track = useRef<HTMLDivElement>(null)
  const [slots, setSlots] = useState<Slot[] | null>(null)
  const [end, setEnd] = useState(booking.end)
  const [busy, setBusy] = useState(false)
  const [openedAt] = useState(() => Date.now())
  // Shown here, not as a toast: in the Manager page this box sits in a Modal that hides toasts.
  const [error, setError] = useState('')
  const step = resource.selection_step_minutes ?? resource.slot_minutes

  useEffect(() => {
    // urgent: a student's view of today would otherwise mark every time "too soon" and hide who has booked it.
    getAvailability(resource.id, sydneyDate(booking.start), step, booking.id, { urgent: !isManager })
      .then((data) => setSlots(data.slots))
      .catch((e: unknown) => setError(errorMessage(e)))
  }, [resource.id, booking.start, booking.id, step, isManager])

  const cells = timelineCells(booking, resource)
  const limit = slots ? latestEnd(booking, slots) : Date.parse(booking.end)
  // Possible ends: the current one, then each later step up to the next booking, closing time and the longest booking.
  const ends = [booking.end, ...extendOptions(booking, resource, resource.max_booking_minutes).filter((t) => Date.parse(t) <= limit)]
  const index = Math.max(0, ends.indexOf(end))
  const span = cells.length * step * 60000
  const at = (iso: string) => `${((Date.parse(iso) - Date.parse(booking.start)) / span) * 100}%`
  const waiting = waitingExtension(booking, openedAt)

  function pick(event: PointerEvent<HTMLDivElement>) {
    const box = track.current?.getBoundingClientRect()
    if (!box) return
    const time = Date.parse(booking.start) + ((event.clientX - box.left) / box.width) * span
    setEnd([...ends].reverse().find((t) => Date.parse(t) <= time + (step * 60000) / 2) ?? booking.end)
    setError('')
  }

  function nudge(event: KeyboardEvent<HTMLButtonElement>) {
    const move = event.key === 'ArrowRight' || event.key === 'ArrowUp' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowDown' ? -1 : 0
    if (!move) return
    event.preventDefault()
    setEnd(ends[Math.min(ends.length - 1, Math.max(0, index + move))])
  }

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

  const kind = (cell: string) => {
    const t = Date.parse(cell)
    return t < Date.parse(booking.end) ? 'mine' : t < Date.parse(end) ? 'added' : t >= limit ? 'taken' : 'free'
  }

  return (
    <div className="bk-resched">
      {waiting && <p className="bk-change-note">Waiting for a Manager: finish at {fmtTime(waiting)}. Asking again replaces it.</p>}
      <div className="ext-track" ref={track} style={{ gridTemplateColumns: `repeat(${cells.length}, 1fr)` }}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pick(e) }}
        onPointerMove={(e) => { if (e.buttons === 1) pick(e) }}>
        {cells.map((cell) => <span key={cell} className={`ext-cell is-${kind(cell)}`} />)}
        <button type="button" role="slider" className="ext-handle" style={{ left: at(end) }} disabled={!slots}
          aria-label="New end time" aria-valuemin={0} aria-valuemax={ends.length - 1} aria-valuenow={index}
          aria-valuetext={fmtTime(end)} onKeyDown={nudge} />
      </div>
      <div className="ext-scale"><span>{fmtTime(booking.start)}</span><span>{fmtClock(resource.closing_time)}</span></div>
      <p className="bk-muted">
        {ends.length === 1 ? 'The time after this booking is taken, or it already ends at closing time or its longest length.'
          : end === booking.end ? 'Drag the end of your booking to the right, or use the arrow keys.'
            : `Finish at ${fmtTime(end)} (+${fmtDuration(minutesBetween(booking.end, end))}).`}
        {!isManager && ' A Manager approves it.'}
      </p>
      {error && <p className="bk-error" role="alert">Not sent: {error}</p>}
      <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
        <button className="ui-btn ui-btn-primary ui-btn-sm" disabled={end === booking.end || busy} onClick={() => void save()}>
          {busy ? 'Sending…' : isManager ? 'Extend now' : 'Ask a Manager'}
        </button>
        <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose}>Close</button>
      </div>
    </div>
  )
}
