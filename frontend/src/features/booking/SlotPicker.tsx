import { useEffect, useRef, useState } from 'react'
import { getAvailability } from './api'
import { errorMessage, fmtTime, QUAL_TEXT, todaySydney, TZ } from './format'
import type { Availability, Resource, Slot } from './types'

interface Props {
  resource: Resource
  /** Slot chosen by the user (start/end are UTC ISO strings from the API). */
  onSelect: (slot: Slot | null) => void
  refreshKey?: number
  hideQualification?: boolean
}

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
          <input type="date" value={date} min={todaySydney()} onChange={(e) => setDate(e.target.value)} />
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
        <button type="button" onClick={() => setReload((n) => n + 1)}>
          Refresh
        </button>
      </div>
      <p className="bk-muted">
        Times shown in {TZ}. Availability is a snapshot and may change before you submit.
      </p>
      {error && <p className="bk-error">{error}</p>}
      {data && !hideQualification && <p className="bk-muted">{QUAL_TEXT[data.qualification_status]}</p>}
      {data && (
        <div className="bk-slots">
          {data.slots.length === 0 && <p>No slots on this day.</p>}
          {data.slots.map((s) => {
            const label = fmtTime(s.start)
            const held = s.reason_code === 'TEMPORARILY_HELD'
            const note = s.available
              ? ''
              : s.reason_code === 'BOOKED'
                ? 'Booked'
                : held
                  ? s.held_by_me
                    ? 'Held by you'
                    : 'Temporarily held'
                  : s.reason_code === 'START_TIME_PASSED'
                    ? 'Passed'
                    : 'Unavailable'
            return (
              <button
                key={s.start}
                type="button"
                className={`bk-slot ${s.available ? '' : 'bk-slot-off'} ${selected === s.start ? 'bk-slot-on' : ''}`}
                disabled={s.reason_code === 'START_TIME_PASSED'}
                title={
                  s.available
                    ? 'Available'
                    : 'Not available: a request here will go to manual review (no hold)'
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
      {data && data.slots.some((s) => !s.available && s.reason_code !== 'START_TIME_PASSED') && (
        <p className="bk-muted">
          Unavailable slots can still be requested; they will go to manual admin review without holding the time.
        </p>
      )}
    </div>
  )
}
