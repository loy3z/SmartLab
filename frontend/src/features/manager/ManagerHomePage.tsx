// 2026-11-07 (client, Week 8): the Manager home page. Admins land on Today (the review queue); a Manager lands here and
// sees the whole lab: what only a Manager decides, rooms and equipment, this week's use, and the booking history lookup.
import { useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { PageHeader, RefreshStamp } from '../../ui/components'
import { getStaffOverview, getUsageReport, listResources, reviewExtension } from '../../api/index.ts'
import { errorMessage, fmtDuration, fmtTime, todaySydney } from '../booking/format'
import type { Booking, Resource, StaffOverview, UsageReport } from '../../api/types/index.ts'
import { MANAGER_DECIDES, todoCards } from '../admin/today'
import { percent } from './usage'
import { busiest, cleanZid, currentWeek, segments, statusCounts } from './manager-home'
import { useAutoRefresh } from '../../lib/use-auto-refresh' // 2026-11-07

export function ManagerHomePage() {
  const navigate = useNavigate()
  const [overview, setOverview] = useState<StaffOverview | null>(null)
  const [resources, setResources] = useState<Resource[]>([])
  const [usage, setUsage] = useState<UsageReport | null>(null)
  const [error, setError] = useState('')
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [zid, setZid] = useState('')
  const [zidError, setZidError] = useState('')
  // 2026-11-07: the Extension requests card (here or on Today) brings the approval list into view, also on phones.
  const [params] = useSearchParams()
  const requestsPanel = useRef<HTMLElement>(null)
  const focusRequests = params.get('focus') === 'extensions'

  const load = useCallback(async () => {
    setLoading(true)
    const week = currentWeek(todaySydney())
    try {
      const [data, list, report] = await Promise.all([getStaffOverview(), listResources({}), getUsageReport(week.first, week.last)])
      setOverview(data)
      setResources(list.results)
      setUsage(report)
      setLoadedAt(Date.now())
      setError('')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])
  useAutoRefresh(() => void load())
  const hasRequests = (overview?.extension_requests ?? []).length > 0
  useEffect(() => {
    if (focusRequests && hasRequests) requestsPanel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [focusRequests, hasRequests])

  function lookUp(event: FormEvent) {
    event.preventDefault()
    const clean = cleanZid(zid)
    if (!clean) return setZidError('Enter a zID: z followed by 7 digits, e.g. z5123456.')
    navigate(`/admin/records?q=${clean}`)
  }

  const counts = statusCounts(resources)
  const decisions = overview ? todoCards(overview).filter((card) => MANAGER_DECIDES.includes(card.key)) : []
  const totals = usage?.totals
  const mostBooked = usage ? busiest(usage.results) : []

  return (
    <section className="today manager-home">
      <PageHeader title="Lab overview" description="Everything a Manager looks after, on one page."
        actions={<RefreshStamp at={loadedAt} onRefresh={() => void load()} busy={loading && loadedAt !== null} />} />
      {error && <p className="bk-error" role="alert">{error}</p>}
      {!overview && loading && <p role="status">Loading…</p>}
      {overview && (
        <>
          {/* 2026-11-09 (Loy feedback): one row of small counts instead of a wall of big cards that are mostly 0. */}
          <h2 className="manager-home-heading">Only a Manager decides</h2>
          {decisions.every((card) => card.count === 0) && <p className="mh-clear">Nothing is waiting for your decision.</p>}
          <div className="mh-chips">
            {decisions.map((card) => (
              <Link key={card.key} to={card.to} className={`mh-chip is-${card.tone}`}
                onClick={card.key === 'extensions' ? () => requestsPanel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) : undefined}>
                <strong>{card.count}</strong> {card.label}
              </Link>
            ))}
            <Link to="/admin/today" className="mh-chip is-grey mh-chip-admin">
              <strong>{overview.pending_bookings + overview.pending_inductions}</strong> Requests and inductions for Admins →
            </Link>
          </div>

          <div className="today-grid">
            {(overview.extension_requests ?? []).length > 0 && (
              <article className="today-panel is-wide" ref={requestsPanel}>
                <h2>Extension requests</h2>
                <p className="bk-muted">People in the lab now who ask to finish later. Approving moves the end if the time after is still free.</p>
                <ul className="today-list">
                  {(overview.extension_requests ?? []).map((booking) => (
                    <ExtensionRow key={`${booking.id}:${booking.extension_end}`} booking={booking}
                      resourceName={resources.find((item) => item.id === booking.resource_id)?.name ?? 'Resource'} onDecided={() => void load()} />
                  ))}
                </ul>
              </article>
            )}
            <article className="today-panel">
              <h2>Rooms and equipment</h2>
              <SplitBar parts={[
                { label: 'open', count: counts.AVAILABLE, color: 'var(--green)' },
                { label: 'under maintenance', count: counts.MAINTENANCE, color: 'var(--amber)' },
                { label: 'closed', count: counts.CLOSED, color: 'var(--red)' },
              ]} empty="No rooms or equipment yet." />
              {overview.out_of_service.length > 0 && (
                <ul className="today-list">
                  {overview.out_of_service.map(({ resource, affected_bookings }) => (
                    <li key={resource.id}>
                      <Link to="/manager/bookings">
                        <strong>{resource.name}</strong> · {resource.status === 'MAINTENANCE' ? 'Under maintenance' : 'Closed'}
                        <span className={affected_bookings ? 'today-due' : 'today-meta'}>{affected_bookings} future booking{affected_bookings === 1 ? '' : 's'}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <p><Link to="/manager/bookings">Room management</Link> · <Link to="/manager/resources">Resources</Link></p>
            </article>

            <article className="today-panel">
              <h2>This week</h2>
              {totals ? (
                <>
                  <p className="manager-home-figures">
                    <span><strong>{fmtDuration(totals.booked_hours * 60)}</strong> booked</span>
                    {totals.utilisation !== null && <span><strong>{percent(totals.utilisation)}</strong> of opening hours</span>}
                  </p>
                  {mostBooked.length > 0 ? (
                    <ul className="mh-usage" aria-label="Most booked this week">
                      {mostBooked.map((row) => (
                        <li key={row.id}>
                          <span className="mh-usage-name">{row.name}</span>
                          <span className="mh-usage-track" aria-hidden="true"><span className="mh-usage-fill" style={{ width: `${row.share}%` }} /></span>
                          <span className="mh-usage-hours">{fmtDuration(row.hours * 60)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="today-empty">Nothing booked this week yet.</p>}
                  <h3 className="mh-subheading">Check-ins so far</h3>
                  <SplitBar parts={[
                    { label: 'checked in', count: totals.checked_in, color: 'var(--green)' },
                    { label: 'missed', count: totals.no_show, color: 'var(--red)' },
                    { label: 'excused', count: totals.excused, color: 'var(--muted)' },
                  ]} empty="No check-ins to count yet this week." />
                </>
              ) : <p className="today-empty">No figures yet.</p>}
              <p>{overview.today_count} booking{overview.today_count === 1 ? '' : 's'} today · <Link to="/admin/records?tab=usage">Usage statistics</Link></p>
            </article>

            <article className="today-panel">
              <h2>Booking history</h2>
              <p className="bk-muted">Every booking of one person over the last year. Only Managers see the full history.</p>
              <form className="ui-filters" onSubmit={lookUp}>
                <input aria-label="zID to look up" placeholder="e.g. z5123456" maxLength={8} value={zid}
                  onChange={(e) => { setZid(e.target.value); setZidError('') }} />
                <button type="submit" className="ui-btn ui-btn-ghost">Look up</button>
              </form>
              {zidError && <p className="bk-error" role="alert">{zidError}</p>}
            </article>

            <article className="today-panel">
              <h2>Lab management</h2>
              <ul className="manager-home-links">
                <li><Link to="/manager/resources">Resources</Link> <span className="bk-muted">rooms, equipment and their internal details</span></li>
                <li><Link to="/manager/users">User management</Link> <span className="bk-muted">roles and staff access</span></li>
                <li><Link to="/manager/setup">Lab setup</Link> <span className="bk-muted">inductions and contact details</span></li>
                <li><Link to="/admin/announcements">Announcements</Link></li>
              </ul>
            </article>
          </div>
        </>
      )}
    </section>
  )
}

/** 2026-11-09: a split bar with its legend, e.g. 20 open · 1 under maintenance · 1 closed. The legend carries the numbers. */
function SplitBar({ parts, empty }: { parts: { label: string; count: number; color: string }[]; empty: string }) {
  const shown = segments(parts)
  if (shown.length === 0) return <p className="today-empty">{empty}</p>
  return (
    <>
      <div className="mh-bar" aria-hidden="true">
        {shown.map((part) => <span key={part.label} style={{ width: `${part.share}%`, background: part.color }} />)}
      </div>
      <ul className="mh-legend">
        {shown.map((part) => (
          <li key={part.label} style={{ '--dot': part.color } as CSSProperties}><strong>{part.count}</strong> {part.label}</li>
        ))}
      </ul>
    </>
  )
}

/** 2026-11-07: one extension request with Approve, or Reject with a reason (shown to the person). */
function ExtensionRow({ booking, resourceName, onDecided }: { booking: Booking; resourceName: string; onDecided: () => void }) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function decide(decision: 'APPROVED' | 'REJECTED') {
    if (!booking.extension_end) return
    setBusy(true)
    setError('')
    try {
      await reviewExtension(booking.id, decision, booking.extension_end, reason.trim())
      onDecided()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="manager-home-request">
      <span><strong>{resourceName}</strong> · {booking.booked_for?.display_name ?? 'Someone'}{' '}
        <span className="today-meta">until {fmtTime(booking.end)}, asks until {fmtTime(booking.extension_end!)}</span></span>
      {rejecting ? (
        <span className="ui-actions">
          <input aria-label="Reason for not approving" placeholder="Reason" maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
          <button type="button" className="ui-btn ui-btn-reject ui-btn-sm" disabled={busy || !reason.trim()} onClick={() => void decide('REJECTED')}>Reject</button>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setRejecting(false)}>Back</button>
        </span>
      ) : (
        <span className="ui-actions">
          <button type="button" className="ui-btn ui-btn-primary ui-btn-sm" disabled={busy} onClick={() => void decide('APPROVED')}>Approve</button>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy} onClick={() => setRejecting(true)}>Reject…</button>
        </span>
      )}
      {error && <span className="bk-error" role="alert">{error}</span>}
    </li>
  )
}
