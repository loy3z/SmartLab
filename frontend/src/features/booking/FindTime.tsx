// Sprint 3: search for a specific time, then review one resource. No queries run while editing filters.
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/auth-context'
import { getDayOverview } from '../../api/index.ts'
import { findDurations, hiddenSummary } from './find-time'
import { errorMessage, fmtClock, fmtDate, fmtDuration, fmtRange, todaySydney, TZ } from './format'
import { CalendarIcon, CheckIcon, SearchIcon } from './icons'
import type { DayOverview, DayOverviewQuery, DayOverviewRow, Resource, ResourceKind } from '../../api/types/index.ts'

function addDays(day: string, days: number) {
  const value = new Date(`${day}T00:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}
const localClock = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

/** The server filters the requested interval. Reuse its actual UTC start when opening the confirmation. */
function matchingSlot(row: DayOverviewRow, query: DayOverviewQuery) {
  return row.slots.find(slot => slot.available && !slot.requested_by_me && localClock.format(new Date(slot.start)) === query.free_at)
}

export function FindTime({ onPick, resources = [] }: {
  onPick: (resource: Resource, start: string, minutes: number, date: string) => void
  resources?: Resource[]
}) {
  const { user } = useAuth()
  const isManager = user?.role === 'MANAGER'
  const [date, setDate] = useState(() => addDays(todaySydney(), user?.bypass_booking_rules || isManager ? 0 : 7))
  const [duration, setDuration] = useState(60)
  const [kind, setKind] = useState<'' | ResourceKind>('')
  const [roomId, setRoomId] = useState('')
  const [category, setCategory] = useState('')
  const [startTime, setStartTime] = useState('09:00')
  const [bookableOnly, setBookableOnly] = useState(true)
  const [query, setQuery] = useState<DayOverviewQuery | null>(null)
  const [data, setData] = useState<DayOverview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const rooms = resources.filter(resource => resource.kind === 'ROOM')
  // Sprint 3 (workspace UI): without a resource list from the page, the filters use the last search's rooms and types.
  const roomChoices = rooms.length ? rooms : data?.rooms ?? []
  const categories = useMemo(() => [...new Set([...resources.map(resource => resource.category).filter((value): value is string => Boolean(value)), ...(data?.categories ?? [])])].sort(), [resources, data?.categories])
  const draft: DayOverviewQuery = { date, duration_minutes: duration, kind: kind || undefined, room_id: roomId || undefined,
    category: kind === 'ROOM' ? undefined : category || undefined, bookable_only: bookableOnly, free_at: startTime }
  const filtersChanged = Boolean(query && JSON.stringify(query) !== JSON.stringify(draft))
  // Sprint 3: the Manager's search follows the resource limit, like the day overview and single booking.
  const caps = resources.map(resource => isManager ? resource.max_booking_minutes
    : resource.effective_max_booking_minutes ?? resource.max_booking_minutes)
  const lengths = findDurations(caps.length ? Math.max(...caps) : undefined)

  useEffect(() => {
    if (!query) return
    let active = true
    getDayOverview(query).then(result => { if (active) setData(result) })
      .catch((reason: unknown) => { if (active) setError(errorMessage(reason)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [query])

  function search(event: FormEvent) {
    event.preventDefault()
    if (loading || !date || !startTime) return
    setError('')
    setData(null)
    setLoading(true)
    setQuery({ ...draft })
  }
  const hidden = hiddenSummary(data?.not_bookable)

  return <section aria-label="Find a free time">
    {/* Sprint 3 (internal-tool UI, AI-2): the tab already says "Find a free time"; no slogan or step marker above the fields. */}
    <form className="bk-find-query" onSubmit={search}>
      <div className="bk-find-primary-fields">
        <label>Date<input type="date" aria-label="Date" required min={todaySydney()} max={data?.latest_date ?? undefined} value={date} onChange={event => setDate(event.target.value)} /></label>
        <label>Start time<input type="time" aria-label="Start time" required step={1800} value={startTime} onChange={event => setStartTime(event.target.value)} /></label>
        <label>Length<select aria-label="Length" value={duration} onChange={event => setDuration(Number(event.target.value))}>{lengths.map(minutes => <option key={minutes} value={minutes}>{fmtDuration(minutes)}</option>)}</select></label>
        <label>Type<select aria-label="Type" value={kind} onChange={event => setKind(event.target.value as '' | ResourceKind)}><option value="">All resources</option><option value="ROOM">Rooms only</option><option value="EQUIPMENT">Equipment only</option></select></label>
        <button type="submit" className="ui-btn ui-btn-primary" disabled={loading}><SearchIcon size={15} />{loading ? 'Searching…' : 'Find available resources'}</button>
      </div>
      <details><summary>More filters</summary><div className="bk-find-secondary-fields">
        <label>Room<select aria-label="Room" value={roomId} onChange={event => setRoomId(event.target.value)}><option value="">All rooms</option>{roomChoices.map(room => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label>
        <label>Equipment type<select aria-label="Equipment type" disabled={kind === 'ROOM'} value={category} onChange={event => setCategory(event.target.value)}><option value="">All types</option>{categories.map(item => <option key={item}>{item}</option>)}</select></label>
      </div></details>
      <label className="bk-find-check"><input type="checkbox" checked={bookableOnly} onChange={event => setBookableOnly(event.target.checked)} />Only show resources I am qualified to book</label>
    </form>
    {error && <p className="bk-error" role="alert">{error}</p>}
    {loading && <div className="bk-find-explainer" role="status"><span className="app-loading-dot" /><p>Checking your chosen time…</p></div>}
    {!query && <div className="bk-find-explainer"><p>Choose a date, start time and length, then search.</p></div>}
    {data && query && <>
      <div className="bk-find-results-head"><h3>{data.count} {data.count === 1 ? 'matching resource' : 'matching resources'}</h3><span>{fmtDate(query.date)}{query.free_at ? ` · ${fmtClock(query.free_at)}` : ''} · {fmtDuration(query.duration_minutes)} · Sydney time</span></div>
      {filtersChanged && <p className="ui-hint" role="status">Your filters have changed. Search again to update these results.</p>}
      {!data.test_bypass && data.latest_date && <p className="bk-muted">Normal booking window: {fmtDate(data.earliest_date)}–{fmtDate(data.latest_date)}.{query.date < data.earliest_date && <> <button type="button" className="bk-linkbtn" onClick={() => setDate(data.earliest_date)}>Use the first bookable day</button> For an earlier date, browse a resource and make an urgent request.</>}</p>}
      {data.count === 0 && <div className="ui-empty"><span className="ui-empty-icon" aria-hidden="true"><SearchIcon size={23} /></span><h3>No matching resources</h3><p>{hidden.text || 'Try a different time, length or resource type.'}</p>{hidden.needsInduction && <Link className="ui-btn ui-btn-ghost" to="/induction">Go to Induction &amp; training</Link>}</div>}
      {data.results.map(row => {
        const slot = matchingSlot(row, query)
        const available = row.can_request && Boolean(slot)
        return <article className="bk-find-result" aria-label={row.resource.name} key={row.resource.id}>
          <span className="bk-find-result-icon" aria-hidden="true"><CalendarIcon size={20} /></span>
          <div><h3>{row.resource.name}</h3><p>{row.room_name ? `In ${row.room_name}` : row.resource.location}{row.resource.capacity ? ` · Up to ${row.resource.capacity} people` : ''}</p>
            <span className={`bk-chip ${available ? 'is-ok' : 'is-warn'}`}>{available ? <><CheckIcon size={12} />Available for your session</> : 'Training or availability requirements apply'}</span>
            {slot && <p>{fmtRange(slot.start, slot.end)}</p>}
          </div>
          <button type="button" className="ui-btn ui-btn-ghost" disabled={!available || filtersChanged} onClick={() => slot && onPick(row.resource, slot.start, query.duration_minutes, query.date)}>Review booking <span aria-hidden="true">↗</span></button>
        </article>
      })}
      {data.count > 0 && hidden.text && <p className="bk-muted">{hidden.text}.{hidden.needsInduction && <> <Link to="/induction">Check your training</Link></>}</p>}
      {Boolean(data.too_long) && <p className="bk-muted">{data.too_long} resources do not support the selected length.</p>}
    </>}
  </section>
}
