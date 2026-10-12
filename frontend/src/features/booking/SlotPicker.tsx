import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { getAvailability } from './api'
import { errorMessage, fmtDate, fmtDateTime, fmtDuration, fmtRange, fmtTime, QUAL_TEXT, todaySydney, TZ } from './format'
import type { Availability, Resource, Slot } from './types'

/** A chosen period: start/end are UTC ISO strings. */
export interface SlotRange {
  start: string
  end: string
  /** Part of the period is booked or awaiting approval for someone else, so the request joins the waitlist. */
  overlapsTaken: boolean
}

interface Props {
  resource: Resource
  onSelect: (range: SlotRange | null) => void
  refreshKey?: number
  hideQualification?: boolean
  /** Reports whether the signed-in user may submit a request (verified induction, resource open). */
  onEligibility?: (canRequest: boolean) => void
  /** Rescheduling: every selection has exactly this length. */
  fixedMinutes?: number
  /** Rescheduling: show this booking's own time as free. */
  excludeBookingId?: string
}

type CellKind = 'free' | 'taken' | 'held' | 'mine' | 'closed'

const OUTSIDE_WINDOW: Slot['reason_code'][] = ['START_TIME_PASSED', 'TOO_SOON', 'TOO_FAR_AHEAD', 'RESOURCE_UNAVAILABLE']

function kindOf(slot: Slot): CellKind {
  if (OUTSIDE_WINDOW.includes(slot.reason_code)) return 'closed'
  if (slot.requested_by_me) return 'mine'
  if (slot.available) return 'free'
  if (slot.reason_code === 'TEMPORARILY_HELD') return 'held'
  return 'taken'
}

function cellTitle(slot: Slot, kind: CellKind): string {
  const when = `${fmtTime(slot.start)} – ${fmtTime(slot.end)}`
  switch (kind) {
    case 'free': return `${when}: available`
    case 'mine': return `${when}: you already have a request here`
    case 'held': return `${when}: awaiting approval for another request${slot.hold_until ? ` (decided by ${fmtDateTime(slot.hold_until)})` : ''}. You can still join the waitlist.`
    case 'taken': return `${when}: booked. You can still join the waitlist.`
    default:
      return `${when}: ${slot.reason_code === 'START_TIME_PASSED' ? 'already passed' : slot.reason_code === 'TOO_SOON' ? 'too soon (book at least a week ahead)' : slot.reason_code === 'TOO_FAR_AHEAD' ? 'too far ahead' : 'not bookable'}`
  }
}

/** Shift a YYYY-MM-DD date by whole days. */
function addDays(ymd: string, days: number): string {
  const date = new Date(`${ymd}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function SlotPicker({ resource, onSelect, refreshKey = 0, hideQualification, onEligibility, fixedMinutes, excludeBookingId }: Props) {
  const [date, setDate] = useState(todaySydney())
  const [data, setData] = useState<Availability | null>(null)
  const [error, setError] = useState('')
  const [range, setRange] = useState<{ from: number; to: number } | null>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [problem, setProblem] = useState('')
  const onSelectRef = useRef(onSelect)
  const onEligibilityRef = useRef(onEligibility)
  useEffect(() => {
    onSelectRef.current = onSelect
    onEligibilityRef.current = onEligibility
  })

  const step = resource.slot_minutes
  const maxCells = Math.max(1, Math.floor((fixedMinutes ?? resource.max_booking_minutes) / step))
  const fixedCells = fixedMinutes ? Math.max(1, Math.round(fixedMinutes / step)) : null

  useEffect(() => {
    let cancelled = false
    getAvailability(resource.id, date, step, excludeBookingId)
      .then((d) => {
        if (cancelled) return
        // Keep the picker inside the booking window the backend reports (e.g. today + 7 to today + 30 days).
        if (d.earliest_date && date < d.earliest_date) return setDate(d.earliest_date)
        if (d.latest_date && date > d.latest_date) return setDate(d.latest_date)
        setData(d)
        onEligibilityRef.current?.(d.can_request)
        setError('')
        setRange(null)
        setProblem('')
        onSelectRef.current(null)
      })
      .catch((e) => !cancelled && (setData(null), setError(errorMessage(e))))
    return () => { cancelled = true }
  }, [resource.id, date, step, excludeBookingId, refreshKey])

  const slots = useMemo(() => data?.slots ?? [], [data])
  const kinds = useMemo(() => slots.map(kindOf), [slots])

  function commit(from: number, to: number) {
    setRange({ from, to })
    setProblem('')
    const overlapsTaken = kinds.slice(from, to + 1).some((k) => k === 'taken' || k === 'held')
    onSelectRef.current({ start: slots[from].start, end: slots[to].end, overlapsTaken })
  }

  function blockedBetween(from: number, to: number): string {
    const bad = kinds.slice(from, to + 1).findIndex((k) => k === 'closed' || k === 'mine')
    if (bad < 0) return ''
    return kinds[from + bad] === 'mine'
      ? 'That period overlaps a request you already made for this resource.'
      : 'That period includes times that cannot be booked.'
  }

  function clear() {
    setRange(null)
    setProblem('')
    onSelectRef.current(null)
  }

  function pick(index: number) {
    if (fixedCells) {
      const to = index + fixedCells - 1
      if (to >= slots.length) return setProblem(`A ${fmtDuration(fixedMinutes!)} booking starting then would run past closing time.`)
      const why = blockedBetween(index, to)
      if (why) return setProblem(why)
      return commit(index, to)
    }
    // Click a start, then click an end. Clicking before or inside the selection starts again.
    if (range && index > range.to) {
      if (index - range.from + 1 > maxCells) {
        return setProblem(`Bookings can be at most ${fmtDuration(resource.max_booking_minutes)} for this resource.`)
      }
      const why = blockedBetween(range.from, index)
      if (why) return setProblem(why)
      return commit(range.from, index)
    }
    if (range && range.from === index && range.to === index) return clear()
    const why = blockedBetween(index, index)
    if (why) return setProblem(why)
    commit(index, index)
  }

  const inPreview = (i: number) =>
    !fixedCells && range && range.from === range.to && hover != null && hover > range.from &&
    i > range.from && i <= hover && hover - range.from < maxCells

  const canRequest = data?.can_request ?? true
  const status = data?.qualification_status
  const resourceClosed = data?.resource_status && data.resource_status !== 'AVAILABLE'
  const selected = range ? { start: slots[range.from]?.start, end: slots[range.to]?.end } : null
  const overlapsTaken = range ? kinds.slice(range.from, range.to + 1).some((k) => k === 'taken' || k === 'held') : false
  const atStart = data?.earliest_date ? date <= data.earliest_date : false
  const atEnd = data?.latest_date ? date >= data.latest_date : false

  return (
    <div>
      {data && !hideQualification && !canRequest && (
        <div className="ui-callout is-warn" role="status">
          <div>
            <strong>{resourceClosed ? `This resource is ${data.resource_status === 'MAINTENANCE' ? 'under maintenance' : 'closed'}` : 'You cannot request this resource yet'}</strong>
            {resourceClosed ? (data.status_reason || 'New requests are paused for now.') : status ? QUAL_TEXT[status] : ''}
          </div>
          {!resourceClosed && status && ['NOT_SUBMITTED', 'REJECTED', 'EXPIRED'].includes(status) && resource.required_qualification_id && (
            <Link className="ui-btn ui-btn-primary ui-btn-sm" to={`/induction?requirement=${resource.required_qualification_id}`}>Upload induction</Link>
          )}
        </div>
      )}

      <div className="ui-tl-head">
        <span className="ui-tl-day">{fmtDate(date)}</span>
        <button type="button" className="ui-icon-btn" aria-label="Previous day" disabled={atStart} onClick={() => setDate(addDays(date, -1))}>‹</button>
        <input
          type="date"
          aria-label="Date"
          value={date}
          min={data?.earliest_date ?? todaySydney()}
          max={data?.latest_date}
          onChange={(e) => e.target.value && setDate(e.target.value)}
        />
        <button type="button" className="ui-icon-btn" aria-label="Next day" disabled={atEnd} onClick={() => setDate(addDays(date, 1))}>›</button>
      </div>
      <p className="bk-muted" style={{ marginTop: 6 }}>
        Times in {TZ}.
        {data?.earliest_date && data.latest_date && <> Bookable from {fmtDate(data.earliest_date)} to {fmtDate(data.latest_date)} ({data.min_advance_days}–{data.max_advance_days} days ahead).</>}
      </p>

      {error && <p className="bk-error">{error}</p>}

      {data && slots.length === 0 && <div className="ui-hint">This resource is not open on this day.</div>}
      {data && slots.length > 0 && (
        <div className="ui-tl">
          <div className="ui-tl-scroll">
            <div style={{ minWidth: slots.length * 26 }}>
              <div className="ui-tl-hours" aria-hidden="true">
                {slots.map((s) => {
                  const label = fmtTime(s.start)
                  return <span key={s.start}>{/:00/.test(label) ? label.replace(':00', '') : ''}</span>
                })}
              </div>
              <div className="ui-tl-grid" role="group" aria-label="Times of day" onMouseLeave={() => setHover(null)}>
                {slots.map((s, i) => {
                  const kind = kinds[i]
                  const sel = range && i >= range.from && i <= range.to
                  const cls = [
                    'ui-tl-cell', `is-${kind}`,
                    sel ? 'is-sel' : '',
                    range && i === range.from ? 'is-sel-start' : '',
                    range && i === range.to ? 'is-sel-end' : '',
                    inPreview(i) ? 'is-preview' : '',
                  ].join(' ')
                  return (
                    <button
                      key={s.start}
                      type="button"
                      className={cls}
                      disabled={kind === 'closed'}
                      aria-pressed={Boolean(sel)}
                      aria-label={cellTitle(s, kind)}
                      title={cellTitle(s, kind)}
                      onMouseEnter={() => setHover(i)}
                      onClick={() => pick(i)}
                    />
                  )
                })}
              </div>
            </div>
          </div>
          <div className="ui-legend">
            <span><i className="lg-free" />Available</span>
            <span><i className="lg-sel" />Your selection</span>
            <span><i className="lg-taken" />Booked</span>
            <span><i className="lg-held" />Awaiting approval</span>
            <span><i className="lg-mine" />Your request</span>
            <span><i className="lg-closed" />Not bookable</span>
          </div>
        </div>
      )}

      {problem && <p className="bk-error" role="alert">{problem}</p>}

      {data && slots.length > 0 && (selected?.start && selected.end ? (
        <div className="ui-selection">
          <div>
            <strong>{fmtRange(selected.start, selected.end)}</strong>
            <span className="ui-sub-text">
              {fmtDuration((Date.parse(selected.end) - Date.parse(selected.start)) / 60000)}
              {!fixedCells && range && range.from === range.to && ' · click a later time to extend'}
            </span>
          </div>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={clear}>Clear</button>
        </div>
      ) : (
        <div className="ui-hint">
          {fixedCells
            ? `Click a start time. The booking keeps its length (${fmtDuration(fixedMinutes!)}).`
            : `Click a start time, then click the end time. Up to ${fmtDuration(resource.max_booking_minutes)}.`}
        </div>
      ))}

      {selected && overlapsTaken && canRequest && (
        <div className="ui-callout is-blue">
          <div>
            <strong>Part of this time is already taken</strong>
            Your request joins the waitlist in submission order. If the time frees up, it moves to an admin for approval.
          </div>
        </div>
      )}
    </div>
  )
}
