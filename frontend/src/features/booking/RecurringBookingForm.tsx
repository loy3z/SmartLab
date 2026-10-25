// Sprint 3: weekly series form (staff only).
import { useMemo, useState } from 'react'
import { useAuth } from '../auth/auth-context'
import { useFeedback } from '../../ui/feedback-context'
import { createSeries, lookupPerson, previewSeries } from './api'
import { errorMessage, fmtDuration, fmtRange, todaySydney } from './format'
import { addDaysIso, isoWeekday, problemDates, SERIES_REASON_TEXT, startTimes, WEEKDAYS } from './series'
import type { PersonBrief, Resource, SeriesPlan, SeriesPreview } from './types'

/**
 * Staff only: book the same time every week. Check the dates first; dates with a problem are skipped (never queued).
 * Every kept date is approved at once because staff create the series; induction and conflicts are still checked.
 */
export function RecurringBookingForm({ resource, onBooked }: { resource: Resource; onBooked: () => void }) {
  const { user } = useAuth()
  const testBypass = Boolean(user?.bypass_booking_rules)
  const feedback = useFeedback()
  const firstDefault = addDaysIso(todaySydney(), testBypass ? 0 : 7)
  const [forOther, setForOther] = useState(false)
  const ownOverride = testBypass && !forOther
  const MAX_WEEKS = ownOverride ? 52 : 14
  const [zid, setZid] = useState('')
  const [person, setPerson] = useState<PersonBrief | null>(null)
  const [weekdays, setWeekdays] = useState<number[]>([isoWeekday(firstDefault)])
  const times = useMemo(() => startTimes(ownOverride ? '00:00' : resource.opening_time,
    ownOverride ? '24:00' : resource.closing_time, resource.slot_minutes), [resource, ownOverride])
  const [startTime, setStartTime] = useState(times.includes('09:00') ? '09:00' : times[0] ?? '09:00')
  const [minutes, setMinutes] = useState(Math.min(60, resource.max_booking_minutes))
  const [firstDate, setFirstDate] = useState(firstDefault)
  const [lastDate, setLastDate] = useState(addDaysIso(firstDefault, 7 * 10 - 1))
  const [purpose, setPurpose] = useState('')
  const [preview, setPreview] = useState<SeriesPreview | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const durations = useMemo(() => {
    const list: number[] = []
    for (let m = resource.slot_minutes; m <= (ownOverride ? 1440 : resource.max_booking_minutes); m += resource.slot_minutes) list.push(m)
    return list
  }, [resource, ownOverride])

  const plan = (): SeriesPlan => ({
    resource_id: resource.id, weekdays: [...weekdays].sort(), start_time: startTime, duration_minutes: minutes,
    first_date: firstDate, last_date: lastDate, ...(forOther && person ? { on_behalf_of_zid: person.zid } : {}),
  })
  const changed = <T,>(setter: (value: T) => void) => (value: T) => { setter(value); setPreview(null); setError('') }

  async function check() {
    if (forOther && !person) return setError('Check the zID of the person first.')
    setBusy(true)
    setError('')
    try {
      setPreview(await previewSeries(plan()))
    } catch (e) {
      setPreview(null)
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function findPerson() {
    const value = zid.trim().toLowerCase()
    if (!/^z\d{7}$/.test(value)) return setError('zID must be z followed by 7 digits, e.g. z5123456.')
    try {
      setPerson(await lookupPerson(value))
      setPreview(null)
      setError('')
    } catch (e) {
      setPerson(null)
      setError(errorMessage(e))
    }
  }

  async function create() {
    if (!preview) return
    const skip = problemDates(preview.occurrences)
    const ok = await feedback.confirm({
      title: `Book ${preview.available_count} date(s)?`,
      details: [
        { label: 'Resource', value: resource.name },
        { label: 'For', value: `${preview.booking_for.display_name} (${preview.booking_for.zid})` },
        { label: 'Every', value: weekdays.map((d) => WEEKDAYS[d - 1].long).join(', ') },
        { label: 'Time', value: `${startTime}, ${fmtDuration(minutes)}` },
        ...(skip.length ? [{ label: 'Skipped', value: `${skip.length} date(s) with a problem` }] : []),
      ],
      message: 'Every date is approved at once and appears in My Bookings.',
      confirmLabel: 'Book series',
    })
    if (!ok.confirmed) return
    setBusy(true)
    try {
      const series = await createSeries({ ...plan(), purpose: purpose.trim(), skip_dates: skip })
      feedback.success(`${series.bookings.length} date(s) booked for ${preview.booking_for.display_name}.`, 'Weekly series booked')
      onBooked()
    } catch (e) {
      setError(errorMessage(e))
      setPreview(null)
    } finally {
      setBusy(false)
    }
  }

  const tooLong = lastDate < firstDate || Date.parse(lastDate) - Date.parse(firstDate) >= MAX_WEEKS * 7 * 86_400_000
  return (
    <div className="bk-series">
      <h2>Repeat weekly: {resource.name}</h2>
      <p className="bk-muted">Staff only. Book the same time every week (up to {MAX_WEEKS} weeks). Dates are approved at once; dates with a problem are skipped.</p>

      <fieldset className="bk-series-row">
        <legend>Book for</legend>
        <label><input type="radio" checked={!forOther} onChange={() => { setForOther(false); setPerson(null); setPreview(null) }} /> Myself</label>
        <label><input type="radio" checked={forOther} onChange={() => { setForOther(true); setPreview(null) }} /> Someone else</label>
        {forOther && (
          <span className="bk-series-person">
            <input aria-label="zID of the person" placeholder="z5123456" value={zid} onChange={(e) => { setZid(e.target.value); setPerson(null) }} />
            <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => void findPerson()}>Check</button>
            {person && <span className="bk-muted">{person.display_name} ({person.zid})</span>}
          </span>
        )}
      </fieldset>

      <fieldset className="bk-series-row">
        <legend>Every</legend>
        {WEEKDAYS.map((day) => (
          <label key={day.value} className="bk-series-day">
            <input type="checkbox" checked={weekdays.includes(day.value)} onChange={(e) => changed(setWeekdays)(
              e.target.checked ? [...weekdays, day.value] : weekdays.filter((d) => d !== day.value))} />
            {day.short}
          </label>
        ))}
      </fieldset>

      <div className="bk-series-row">
        <label>Start
          <select aria-label="Start time" value={startTime} onChange={(e) => changed(setStartTime)(e.target.value)}>
            {times.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>Length
          <select aria-label="Length" value={minutes} onChange={(e) => changed(setMinutes)(Number(e.target.value))}>
            {durations.map((m) => <option key={m} value={m}>{fmtDuration(m)}</option>)}
          </select>
        </label>
        <label>From
          <input type="date" aria-label="First date" value={firstDate} onChange={(e) => e.target.value && changed(setFirstDate)(e.target.value)} />
        </label>
        <label>Until
          <input type="date" aria-label="Last date" value={lastDate} onChange={(e) => e.target.value && changed(setLastDate)(e.target.value)} />
        </label>
      </div>
      {tooLong && <p className="bk-error">Choose a last date on or after the first date, at most {MAX_WEEKS} weeks later.</p>}

      <label className="bk-series-purpose">Purpose
        <textarea rows={2} maxLength={1000} value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="e.g. Weekly COMP lab session" />
      </label>

      {error && <p className="bk-error" role="alert">{error}</p>}
      <div className="bk-series-actions">
        <button type="button" className="ui-btn ui-btn-ghost" disabled={busy || weekdays.length === 0 || tooLong} onClick={() => void check()}>
          {busy && !preview ? 'Checking…' : 'Check dates'}
        </button>
        <button type="button" className="ui-btn ui-btn-primary" disabled={busy || !preview || preview.available_count === 0 || !purpose.trim()}
          onClick={() => void create()}>
          {preview ? `Book ${preview.available_count} date(s)` : 'Book series'}
        </button>
      </div>

      {preview && (
        <table className="ui-table bk-series-table" aria-label="Dates in this series">
          <thead><tr><th>Date</th><th>Result</th></tr></thead>
          <tbody>
            {preview.occurrences.map((item) => (
              <tr key={item.date} className={item.available ? undefined : 'is-skipped'}>
                <td>{fmtRange(item.start, item.end)}</td>
                <td>{item.available ? 'Will be booked' : `Skipped: ${SERIES_REASON_TEXT[item.reason_code ?? ''] ?? item.message ?? item.reason_code}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
