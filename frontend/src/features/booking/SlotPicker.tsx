import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { getAvailability } from './api'
import { errorMessage, fmtDate, fmtDuration, fmtRange, fmtTime, QUAL_TEXT, todaySydney, TZ } from './format'
import { addDays, dateRange } from './slot-picker' // Sprint 3 (2026-10-25 cleanup): moved out of this file
import { cellTitle, kindOf } from './slot-cells'
import { NowLegend, NowLine } from './NowLine' // Sprint 3 (1.15.0)
import type { Availability, Resource } from './types'

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
  /** Admin/Manager booking on behalf of someone: their eligibility and requests. */
  forZid?: string
  /** Urgent request: only the days before the normal booking window (today up to earliest_date - 1). */
  urgent?: boolean
  /** Manager reschedule: from today up to the latest date (the minimum advance window does not apply). */
  allowEarly?: boolean
  /** Day to open on (YYYY-MM-DD, Sydney), e.g. the booking being rescheduled. */
  initialDate?: string
  /** Pre-select a period once the day has loaded (UTC ISO start, length in minutes), e.g. from the day grid. */
  initialStart?: string
  initialMinutes?: number
  /** Sprint 3 (1.16.0): offer the urgent route when someone is on the first normal day and wants an earlier one. */
  onAskEarlier?: () => void
  /** Sprint 3 (1.16.0): replaces the "joins the waitlist" text when part of the chosen time is taken (change requests). */
  takenNote?: string
}



export function SlotPicker({ resource, onSelect, refreshKey = 0, hideQualification, onEligibility, fixedMinutes, excludeBookingId, forZid, urgent = false, allowEarly = false, initialDate, initialStart, initialMinutes, onAskEarlier, takenNote }: Props) {
  const [date, setDate] = useState(initialDate ?? todaySydney())
  const [data, setData] = useState<Availability | null>(null)
  const [error, setError] = useState('')
  const [range, setRange] = useState<{ from: number; to: number } | null>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [problem, setProblem] = useState('')
  // Sprint 3 (workspace UI): coming from Find a free time (a start is given), the day grid starts folded; the
  // Start / Length selects below stay visible either way.
  const [showTimeline, setShowTimeline] = useState(!initialStart)
  // Sprint 3 (1.16.0): length used by the "Start / Length" selects (cells of `step` minutes); 1 hour by default.
  const [wantedCells, setWantedCells] = useState<number | null>(null)
  // Sprint 3 (2026-10-25): the day timeline scrolls sideways; a desktop mouse wheel scrolls it too.
  const timelineRef = useRef<HTMLDivElement>(null)
  // Applied once, on the first load of the initial day; later days and refreshes start empty as before.
  const pendingInitial = useRef(initialStart && initialMinutes ? { start: initialStart, minutes: initialMinutes } : null)
  const onSelectRef = useRef(onSelect)
  const onEligibilityRef = useRef(onEligibility)
  useEffect(() => {
    onSelectRef.current = onSelect
    onEligibilityRef.current = onEligibility
  })

  // Sprint 3 (2026-10-25): a mouse wheel over the day timeline scrolls it sideways (Windows wheels have no
  // horizontal axis). Passive: false so the page itself does not scroll while the timeline moves.
  useEffect(() => {
    const el = timelineRef.current
    if (!el) return
    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) return
      if (el.scrollWidth <= el.clientWidth) return
      event.preventDefault()
      el.scrollLeft += event.deltaY
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [showTimeline])

  const step = resource.slot_minutes
  const maximumMinutes = data?.max_booking_minutes ?? resource.max_booking_minutes
  const maxCells = Math.max(1, Math.floor((fixedMinutes ?? maximumMinutes) / step))
  const fixedCells = fixedMinutes ? Math.max(1, Math.round(fixedMinutes / step)) : null

  useEffect(() => {
    let cancelled = false
    getAvailability(resource.id, date, step, excludeBookingId, { forZid, urgent: urgent || allowEarly })
      .then((d) => {
        if (cancelled) return
        // Keep the picker inside the booking window the backend reports (e.g. today + 7 to today + 30 days).
        // Urgent: only the days before that window. Manager reschedule: from today.
        const { earliest, latest } = dateRange(d, urgent, allowEarly)
        if (earliest && date < earliest) return setDate(earliest)
        if (latest && date > latest && latest >= (earliest ?? latest)) return setDate(latest)
        setData(d)
        onEligibilityRef.current?.(d.can_request)
        setError('')
        setRange(null)
        setProblem('')
        onSelectRef.current(null)
        const wanted = pendingInitial.current
        pendingInitial.current = null
        if (wanted) {
          const from = d.slots.findIndex((s) => Date.parse(s.start) === Date.parse(wanted.start))
          const to = from + Math.max(1, Math.round(wanted.minutes / step)) - 1
          if (from >= 0 && to < d.slots.length && d.slots.slice(from, to + 1).every((s) => kindOf(s) === 'free')) {
            setRange({ from, to })
            onSelectRef.current({ start: d.slots[from].start, end: d.slots[to].end, overlapsTaken: false })
          }
        }
      })
      .catch((e) => {
        if (cancelled) return
        // Never leave an old selection usable after a failed refresh.
        setData(null)
        setRange(null)
        setError(errorMessage(e))
        onSelectRef.current(null)
        onEligibilityRef.current?.(false)
      })
    return () => { cancelled = true }
  }, [resource.id, date, step, excludeBookingId, refreshKey, forZid, urgent, allowEarly])

  /** Changing the day drops the current selection and pauses submitting until the new day has loaded. */
  function changeDate(next: string) {
    if (next === date) return
    setRange(null)
    setProblem('')
    setData(null)
    onSelectRef.current(null)
    onEligibilityRef.current?.(false)
    setDate(next)
  }

  const slots = useMemo(() => data?.slots ?? [], [data])
  const kinds = useMemo(() => slots.map(kindOf), [slots])

  function commit(from: number, to: number) {
    setRange({ from, to })
    setProblem('')
    const overlapsTaken = kinds.slice(from, to + 1).some((k) => k === 'taken' || k === 'held')
    onSelectRef.current({ start: slots[from].start, end: slots[to].end, overlapsTaken })
  }

  function blockedBetween(from: number, to: number): string {
    // An urgent request or a reschedule needs free time: it never joins the waitlist.
    const strict = urgent || allowEarly || data?.test_bypass
    const bad = kinds.slice(from, to + 1).findIndex((k) => k === 'closed' || k === 'mine' || (strict && (k === 'taken' || k === 'held')))
    if (bad < 0) return ''
    const kind = kinds[from + bad]
    return kind === 'mine'
      ? `That period overlaps a request ${forZid ? 'this person already has' : 'you already made'} for this resource.`
      : kind === 'closed' ? 'That period includes times that cannot be booked.'
        : 'Choose a free time: this period is booked or awaiting approval.'
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
        return setProblem(`Bookings can be at most ${fmtDuration(maximumMinutes)} for this resource.`)
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

  // Sprint 3 (1.16.0): choose by "Start" and "Length" instead of tapping narrow cells (phones). Same checks as clicking.
  const defaultCells = fixedCells ?? Math.max(1, Math.min(maxCells, Math.round(60 / step)))
  const lengthCells = fixedCells ?? wantedCells ?? (range ? range.to - range.from + 1 : defaultCells)
  function chooseByInputs(from: number, cells: number) {
    const to = from + cells - 1
    if (to >= slots.length) return setProblem(`A ${fmtDuration(cells * step)} booking starting then would run past closing time.`)
    const why = blockedBetween(from, to)
    if (why) return setProblem(why)
    commit(from, to)
  }
  const strictInputs = urgent || allowEarly || data?.test_bypass
  const startOptions = slots
    .map((slot, index) => ({ index, label: fmtTime(slot.start), kind: kinds[index] }))
    .filter((item) => item.kind !== 'closed' && item.kind !== 'mine' && !(strictInputs && (item.kind === 'taken' || item.kind === 'held')))
  const lengthOptions = Array.from({ length: maxCells }, (_, i) => i + 1)

  const inPreview = (i: number) =>
    !fixedCells && range && range.from === range.to && hover != null && hover > range.from &&
    i > range.from && i <= hover && hover - range.from < maxCells

  const canRequest = data?.can_request ?? true
  const status = data?.qualification_status
  const resourceClosed = data?.resource_status && data.resource_status !== 'AVAILABLE'
  const selected = range ? { start: slots[range.from]?.start, end: slots[range.to]?.end } : null
  const overlapsTaken = range ? kinds.slice(range.from, range.to + 1).some((k) => k === 'taken' || k === 'held') : false
  const { earliest: earliestDate, latest: latestDate } = dateRange(data, urgent, allowEarly)
  const atStart = earliestDate ? date <= earliestDate : false
  const noUrgentDays = urgent && earliestDate && latestDate ? latestDate < earliestDate : false
  const person = forZid && data?.booking_for ? `${data.booking_for.display_name} (${data.booking_for.zid})` : ''
  const atEnd = latestDate ? date >= latestDate : false

  return (
    <div>
      {data && !hideQualification && !canRequest && (
        <div className="ui-callout is-warn" role="status">
          <div>
            <strong>{resourceClosed ? `This resource is ${data.resource_status === 'MAINTENANCE' ? 'under maintenance' : 'closed'}` : person ? `${person} cannot be booked for this resource yet` : 'You cannot request this resource yet'}</strong>
            {resourceClosed ? (data.status_reason || 'New requests are paused for now.')
              : person ? `Their induction status is ${status?.replaceAll('_', ' ').toLowerCase()}. The same induction rules apply to everyone.`
                : status ? QUAL_TEXT[status] : ''}
          </div>
          {!person && !resourceClosed && status && ['NOT_SUBMITTED', 'REJECTED', 'EXPIRED', 'EXPIRES_BEFORE_END'].includes(status) && resource.required_qualification_id && (
            <Link className="ui-btn ui-btn-primary ui-btn-sm" to={`/induction?requirement=${resource.required_qualification_id}`}>Upload induction</Link>
          )}
          {!person && !resourceClosed && status === 'PREREQUISITE_REQUIRED' && data.missing_prerequisite_id && (
            <Link className="ui-btn ui-btn-primary ui-btn-sm" to={`/induction?requirement=${data.missing_prerequisite_id}`}>Open General induction</Link>
          )}
        </div>
      )}

      <div className="ui-tl-head">
        <span className="ui-tl-day">{fmtDate(date)}</span>
        <button type="button" className="ui-icon-btn" aria-label="Previous day" disabled={atStart} onClick={() => changeDate(addDays(date, -1))}>‹</button>
        <input
          type="date"
          aria-label="Date"
          value={date}
          min={earliestDate ?? todaySydney()}
          max={latestDate}
          onChange={(e) => e.target.value && changeDate(e.target.value)}
        />
        <button type="button" className="ui-icon-btn" aria-label="Next day" disabled={atEnd} onClick={() => changeDate(addDays(date, 1))}>›</button>
      </div>
      <p className="bk-muted" style={{ marginTop: 6 }}>
        Times in {TZ}.
        {data?.test_bypass && <> Test overrides: choose a future time, up to 24 h. Booking windows and training checks are bypassed; conflicts still apply.</>}
        {urgent && earliestDate && latestDate && !noUrgentDays && <> Urgent: {fmtDate(earliestDate)} to {fmtDate(latestDate)}, before the normal booking window. Only free times can be chosen.</>}
        {noUrgentDays && <> You can already book from today, so an urgent request is not needed.</>}
        {allowEarly && earliestDate && latestDate && <> Manager reschedule: {fmtDate(earliestDate)} to {fmtDate(latestDate)}. Only free times can be chosen.</>}
        {!urgent && !allowEarly && data?.earliest_date && data.latest_date && <> Bookable from {fmtDate(data.earliest_date)} to {fmtDate(data.latest_date)} ({data.min_advance_days}–{data.max_advance_days} days ahead).</>}
      </p>
      {/* Sprint 3 (1.16.0): someone who wants an earlier day used to see only a disabled "previous day" button. */}
      {onAskEarlier && !urgent && !allowEarly && atStart && data?.earliest_date && data.earliest_date > todaySydney() && (
        <div className="ui-hint bk-earlier">
          Need a date before {fmtDate(data.earliest_date)}?
          <button type="button" className="bk-linkbtn" onClick={onAskEarlier}>Make an urgent request</button>
        </div>
      )}

      {error && <p className="bk-error">{error}</p>}

      {data && slots.length === 0 && <div className="ui-hint">This resource is not open on this day.</div>}
      {data && slots.length > 0 && <button type="button" className="bk-linkbtn bk-timeline-toggle" aria-expanded={showTimeline} onClick={() => setShowTimeline(value => !value)}>{showTimeline ? 'Hide day availability' : 'View day availability'}</button>}
      {data && slots.length > 0 && showTimeline && (
        <div className="ui-tl">
          <div className="ui-tl-scroll" ref={timelineRef}>
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
                      aria-label={cellTitle(s, kind, data.min_advance_days, data.max_advance_days)}
                      title={cellTitle(s, kind, data.min_advance_days, data.max_advance_days)}
                      onMouseEnter={() => setHover(i)}
                      onClick={() => pick(i)}
                    />
                  )
                })}
                <NowLine slots={slots} />{/* Sprint 3 (1.15.0) */}
              </div>
            </div>
          </div>
          <div className="ui-legend">
            <span><i className="lg-free" />Available</span>
            <span><i className="lg-sel" />Your selection</span>
            <span><i className="lg-taken" />Booked</span>
            <span><i className="lg-held" />Awaiting approval</span>
            <span><i className="lg-mine" />{forZid ? 'Their request' : 'Your request'}</span>
            <span><i className="lg-closed" />Not bookable</span>
            <NowLegend slots={slots} />{/* Sprint 3 (1.15.0) */}
          </div>
        </div>
      )}

      {/* Sprint 3 (1.16.0): the same choice with two selects (easier than tapping cells on a phone). */}
      {data && slots.length > 0 && canRequest && startOptions.length > 0 && (
        <div className="ui-tl-inputs">
          <label>Start
            <select aria-label="Start time" value={range ? range.from : ''} onChange={(e) => e.target.value !== '' && chooseByInputs(Number(e.target.value), lengthCells)}>
              <option value="" disabled>Choose</option>
              {startOptions.map((item) => <option key={item.index} value={item.index}>{item.label}{item.kind === 'free' ? '' : ' (waitlist)'}</option>)}
            </select>
          </label>
          {!fixedCells && (
            <label>Length
              <select aria-label="Length" value={lengthCells} onChange={(e) => {
                const cells = Number(e.target.value)
                setWantedCells(cells)
                if (range) chooseByInputs(range.from, cells)
              }}>
                {lengthOptions.map((cells) => <option key={cells} value={cells}>{fmtDuration(cells * step)}</option>)}
              </select>
            </label>
          )}
        </div>
      )}

      {problem && <p className="bk-error" role="alert">{problem}</p>}

      {data && slots.length > 0 && (selected?.start && selected.end ? (
        <div className="ui-selection">
          <div>
            <strong>{fmtRange(selected.start, selected.end)}</strong>
            <span className="ui-sub-text">
              {fmtDuration((Date.parse(selected.end) - Date.parse(selected.start)) / 60000)}
              {!fixedCells && showTimeline && range && range.from === range.to && ' · click a later time to extend'}
            </span>
          </div>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={clear}>Clear</button>
        </div>
      ) : (
        <div className="ui-hint">
          {fixedCells
            ? `Click a start time. The booking keeps its length (${fmtDuration(fixedMinutes!)}).`
            : `Click a start time, then click the end time. Up to ${fmtDuration(maximumMinutes)}.`}
        </div>
      ))}

      {selected && overlapsTaken && canRequest && (
        <div className="ui-callout is-blue">
          <div>
            <strong>Part of this time is already taken</strong>
            {takenNote ?? 'Your request joins the waitlist in submission order. If the time frees up, it moves to an admin for approval.'}
          </div>
        </div>
      )}
    </div>
  )
}
