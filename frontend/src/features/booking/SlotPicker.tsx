import { useEffect, useRef, useState } from 'react'
import { getAvailability } from './api'
import { errorMessage, fmtDate, fmtTime, QUAL_TEXT, todaySydney, TZ } from './format'
import type { Availability, Resource, Slot } from './types'

interface Props {
  resource: Resource
  /** Slot chosen by the user (start/end are UTC ISO strings from the API). */
  onSelect: (slot: Slot | null) => void
  refreshKey?: number
  hideQualification?: boolean
}

/** Slots that cannot be requested at all (past, or outside the booking window). */
const OUTSIDE_WINDOW: Slot['reason_code'][] = ['START_TIME_PASSED', 'TOO_SOON', 'TOO_FAR_AHEAD']

function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 15000)
    return () => clearInterval(t)
  }, [])
  const mins = Math.max(0, Math.ceil((new Date(until).getTime() - now) / 60000))
  return <small> (held ~{mins} min)</small>
}

export function SlotPicker({ resource, onSelect, refreshKey = 0, hideQualification }: Props) {
  const [date, setDate] = useState(todaySydney())
  const [duration, setDuration] = useState(resource.slot_minutes)
  const [data, setData] = useState<Availability | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const onSelectRef = useRef(onSelect)
  useEffect(() => {
    onSelectRef.current = onSelect
  })

  useEffect(() => {
    let cancelled = false
    getAvailability(resource.id, date, duration)
      .then((d) => {
        if (cancelled) return
        // Keep the picker inside the booking window the backend reports (e.g. today + 7 to today + 30 days).
        if (d.earliest_date && date < d.earliest_date) return setDate(d.earliest_date)
        if (d.latest_date && date > d.latest_date) return setDate(d.latest_date)
        setData(d)
        setError('')
        setSelected(null)
        onSelectRef.current(null)
      })
      .catch((e) => !cancelled && (setData(null), setError(errorMessage(e))))
    return () => {
      cancelled = true
    }
  }, [resource.id, date, duration, refreshKey, reload])

  const durations: number[] = []
  for (let m = resource.slot_minutes; m <= resource.max_booking_minutes; m += resource.slot_minutes) {
    durations.push(m)
  }

  return (
    <div>
      <div className="bk-row">
        <label>
          Date{' '}
          <input
            type="date"
            value={date}
            min={data?.earliest_date ?? todaySydney()}
            max={data?.latest_date}
            onChange={(e) => e.target.value && setDate(e.target.value)}
          />
        </label>
        <label>
          Duration{' '}
          <select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
            {durations.map((m) => (
              <option key={m} value={m}>
                {m} min
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="bk-btn-outline bk-sm" onClick={() => setReload((n) => n + 1)}>
          Refresh
        </button>
      </div>
      <p className="bk-muted">
        Times shown in {TZ}. Availability is a snapshot and may change before you submit.
        {data?.earliest_date && data.latest_date && (
          <>
            <br />
            Bookings must be made {data.min_advance_days} to {data.max_advance_days} days ahead: from{' '}
            {fmtDate(data.earliest_date)} to {fmtDate(data.latest_date)}.
          </>
        )}
      </p>
      {error && <p className="bk-error">{error}</p>}
      {data && !hideQualification && <p className="bk-muted">{QUAL_TEXT[data.qualification_status]}</p>}
      {data && (
        <div className="bk-slots">
          {data.slots.length === 0 && <p>No slots on this day.</p>}
          {data.slots.map((s) => {
            const label = fmtTime(s.start)
            const held = s.reason_code === 'TEMPORARILY_HELD'
            const mine = s.requested_by_me
            const note = mine
              ? 'Already requested'
              : s.available
                ? ''
                : s.reason_code === 'BOOKED'
                  ? 'Booked'
                  : held
                    ? s.held_by_me
                      ? 'Held by you'
                      : 'Temporarily held'
                    : s.reason_code === 'START_TIME_PASSED'
                      ? 'Passed'
                      : s.reason_code === 'TOO_SOON'
                        ? 'Too soon'
                        : s.reason_code === 'TOO_FAR_AHEAD'
                          ? 'Too far ahead'
                          : 'Unavailable'
            const closed = mine || OUTSIDE_WINDOW.includes(s.reason_code)
            return (
              <button
                key={s.start}
                type="button"
                className={`bk-slot ${s.available && !mine ? '' : 'bk-slot-off'} ${selected === s.start ? 'bk-slot-on' : ''}`}
                disabled={closed}
                title={
                  mine
                    ? 'You already have an overlapping request for this resource'
                    : s.available
                      ? 'Available'
                      : closed
                        ? 'Not bookable on this date'
                        : 'Taken: a request here joins the waitlist and is approved automatically if the time frees up'
                }
                onClick={() => {
                  setSelected(s.start)
                  onSelect(s)
                }}
              >
                {label}
                {note && <small> {note}</small>}
                {held && s.hold_until && <Countdown until={s.hold_until} />}
              </button>
            )
          })}
        </div>
      )}
      {data && data.slots.some((s) => !s.available && !OUTSIDE_WINDOW.includes(s.reason_code)) && (
        <p className="bk-muted">
          Booked or held times can still be requested: you join the waitlist in submission order and are approved
          automatically if the time frees up and your induction is verified. You cannot submit the same resource and
          overlapping time twice.
        </p>
      )}
    </div>
  )
}
