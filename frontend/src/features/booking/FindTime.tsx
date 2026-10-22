import { useEffect, useMemo, useState } from 'react'
import { getDayOverview } from './api'
import { errorMessage, fmtDate, fmtTime, QUAL_TEXT, todaySydney, TZ } from './format'
import { cellTitle, kindOf } from './slot-cells'
import type { DayOverview, DayOverviewRow, Resource, ResourceKind } from './types'

const DURATIONS = [30, 60, 90, 120, 180, 240]
// Opening hours of the demo resources (08:00-20:00); "Free at" offers each half hour.
const START_TIMES = Array.from({ length: 24 }, (_, i) => `${String(8 + Math.floor(i / 2)).padStart(2, '0')}:${i % 2 ? '30' : '00'}`)

function addDays(ymd: string, days: number): string {
  const date = new Date(`${ymd}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function rowNote(row: DayOverviewRow): string {
  if (row.resource_status !== 'AVAILABLE') return row.resource_status === 'MAINTENANCE' ? 'Under maintenance' : 'Closed'
  if (!row.can_request) return QUAL_TEXT[row.qualification_status] ?? 'Not available to you'
  return ''
}

/**
 * "Find a free time": filters, then one row per resource with that day's free and taken times. Clicking a free
 * time opens the booking form with the resource and period already chosen. Same rules as each resource's own
 * availability (the backend runs one shared check).
 */
export function FindTime({ onPick }: { onPick: (resource: Resource, start: string, minutes: number, date: string) => void }) {
  const [date, setDate] = useState(todaySydney())
  const [duration, setDuration] = useState(60)
  const [kind, setKind] = useState<'' | ResourceKind>('')
  const [roomId, setRoomId] = useState('')
  const [category, setCategory] = useState('')
  const [freeAt, setFreeAt] = useState('')
  const [bookableOnly, setBookableOnly] = useState(true)
  const [data, setData] = useState<DayOverview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getDayOverview({
      date, duration_minutes: duration, kind: kind || undefined, room_id: roomId || undefined,
      category: kind === 'ROOM' ? undefined : category || undefined, bookable_only: bookableOnly, free_at: freeAt || undefined,
    })
      .then((d) => {
        if (cancelled) return
        // Open on the first bookable day (today + 7 by default) and stay inside the booking window.
        if (date < d.earliest_date) return setDate(d.earliest_date)
        if (date > d.latest_date) return setDate(d.latest_date)
        setData(d)
        setError('')
      })
      .catch((e: unknown) => !cancelled && (setData(null), setError(errorMessage(e))))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [date, duration, kind, roomId, category, freeAt, bookableOnly])

  const header = useMemo(() => data?.results[0]?.slots ?? [], [data])
  const atStart = data ? date <= data.earliest_date : true
  const atEnd = data ? date >= data.latest_date : true

  return (
    <section aria-label="Find a free time">
      <div className="bk-find-filters">
        <label>Date
          <span className="bk-find-date">
            <button type="button" className="ui-icon-btn" aria-label="Previous day" disabled={atStart} onClick={() => setDate(addDays(date, -1))}>‹</button>
            <input type="date" aria-label="Date" value={date} min={data?.earliest_date} max={data?.latest_date}
              onChange={(e) => e.target.value && setDate(e.target.value)} />
            <button type="button" className="ui-icon-btn" aria-label="Next day" disabled={atEnd} onClick={() => setDate(addDays(date, 1))}>›</button>
          </span>
        </label>
        <label>Length
          <select aria-label="Length" value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
            {DURATIONS.map((m) => <option key={m} value={m}>{m < 60 ? `${m} min` : `${m / 60} hour${m === 60 ? '' : 's'}`}</option>)}
          </select>
        </label>
        <label>Free at
          <select aria-label="Free at" value={freeAt} onChange={(e) => setFreeAt(e.target.value)}>
            <option value="">Any time</option>
            {START_TIMES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>Type
          <select aria-label="Type" value={kind} onChange={(e) => setKind(e.target.value as '' | ResourceKind)}>
            <option value="">Rooms and equipment</option>
            <option value="ROOM">Rooms only</option>
            <option value="EQUIPMENT">Equipment only</option>
          </select>
        </label>
        <label>Room
          <select aria-label="Room" value={roomId} onChange={(e) => setRoomId(e.target.value)}>
            <option value="">All rooms</option>
            {data?.rooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
          </select>
        </label>
        <label>Equipment type
          <select aria-label="Equipment type" value={category} disabled={kind === 'ROOM'} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All types</option>
            {data?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>
      <label className="bk-find-check">
        <input type="checkbox" checked={bookableOnly} onChange={(e) => setBookableOnly(e.target.checked)} />
        Only show what I can book now
      </label>

      <p className="bk-muted">
        {fmtDate(date)} · times in {TZ}. {data && <>Bookable from {fmtDate(data.earliest_date)} to {fmtDate(data.latest_date)}.</>} Click a free time to book it.
      </p>
      {error && <p className="bk-error" role="alert">{error}</p>}
      {loading && !data && <p role="status">Loading free times…</p>}
      {data && data.count === 0 && (
        <div className="ui-hint">
          {bookableOnly ? 'Nothing you can book matches these filters. Untick “Only show what I can book now” to see everything.' : 'Nothing matches these filters.'}
        </div>
      )}

      {data && data.count > 0 && (
        <div className="ui-tl-scroll">
          <div className="bk-find-table" style={{ minWidth: 210 + header.length * 26 }}>
            <div className="bk-find-row" aria-hidden="true">
              <span />
              <div className="ui-tl-hours">
                {header.map((s) => {
                  const label = fmtTime(s.start)
                  return <span key={s.start}>{/:00/.test(label) ? label.replace(':00', '') : ''}</span>
                })}
              </div>
            </div>
            {data.results.map((row) => {
              const note = rowNote(row)
              return (
                <div key={row.resource.id} className="bk-find-row">
                  <div className="bk-find-name">
                    <b>{row.resource.name}</b>
                    <small>{[row.room_name, row.resource.category].filter(Boolean).join(' · ') || (row.resource.kind === 'ROOM' ? 'Room' : '')}</small>
                    {note && <small className="bk-find-note">{note}</small>}
                  </div>
                  <div className="ui-tl-grid" role="group" aria-label={`Times for ${row.resource.name}`}>
                    {row.slots.map((s) => {
                      const k = kindOf(s)
                      const usable = k === 'free' && row.can_request
                      const title = row.can_request ? cellTitle(s, k, data.min_advance_days, data.max_advance_days) : `${fmtTime(s.start)}: ${note}`
                      return (
                        <button key={s.start} type="button" className={`ui-tl-cell bk-find-cell is-${row.can_request ? k : 'closed'}`}
                          disabled={!usable} title={title} aria-label={`${row.resource.name}, ${title}`}
                          onClick={() => onPick(row.resource, s.start, duration, date)} />
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="ui-legend">
            <span><i className="lg-free" />Free</span>
            <span><i className="lg-taken" />Booked</span>
            <span><i className="lg-held" />Awaiting approval</span>
            <span><i className="lg-mine" />Your request</span>
            <span><i className="lg-closed" />Not bookable</span>
          </div>
        </div>
      )}
    </section>
  )
}
