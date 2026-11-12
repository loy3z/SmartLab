// 2026-11-07 (client, Week 8): the Manager home page. Admins land on Today (the review queue); a Manager lands here and
// sees the whole lab: what only a Manager decides, rooms and equipment, this week's use, and the booking history lookup.
import { useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { PageHeader, RefreshStamp } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { getStaffOverview, getUsageReport, listResources, reviewExtension } from '../../api/index.ts'
import { errorMessage, fmtDuration, fmtTime, todaySydney } from '../booking/format'
import type { Booking } from '../../api/types/index.ts'
import { MANAGER_DECIDES, todoCards } from '../admin/today'
import { percent } from './usage'
import { busiest, cleanZid, currentWeek, segments, statusCounts } from './manager-home'
import { useAutoRefresh } from '../../lib/use-auto-refresh' // 2026-11-07

export function ManagerHomePage() {
  const navigate = useNavigate()
  const [overviewSection, reloadOverview, setOverviewSection] = useSection(getStaffOverview)
  const [resourcesSection, reloadResources] = useSection(loadResourceList)
  const [usageSection, reloadUsage] = useSection(loadWeeklyUsage)
  const [zid, setZid] = useState('')
  const [zidError, setZidError] = useState('')
  const zidInput = useRef<HTMLInputElement>(null)
  const requestsHeading = useRef<HTMLHeadingElement>(null)
  const { search, key: locationKey } = useLocation()
  const focusRequests = new URLSearchParams(search).get('focus') === 'extensions'
  const overview = overviewSection.data
  const resources = resourcesSection.data
  const usage = usageSection.data

  const load = useCallback(() => {
    void reloadOverview()
    void reloadResources()
    void reloadUsage()
  }, [reloadOverview, reloadResources, reloadUsage])

  useEffect(() => {
    load()
  }, [load])
  useAutoRefresh(load)
  const extensionRequests = overview?.extension_requests ?? []
  const hasRequests = extensionRequests.length > 0
  const approvalsLoaded = overview !== null
  useEffect(() => {
    const heading = requestsHeading.current
    if (!focusRequests || !approvalsLoaded || !heading) return
    heading.focus({ preventScroll: true })
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    heading.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
  }, [focusRequests, approvalsLoaded, locationKey])

  function lookUp(event: FormEvent) {
    event.preventDefault()
    const clean = cleanZid(zid)
    if (!clean) {
      setZidError('Enter a zID: z followed by 7 digits, e.g. z5123456.')
      zidInput.current?.focus()
      return
    }
    navigate(`/admin/records?q=${clean}`)
  }

  function extensionDecided(booking: Booking) {
    setOverviewSection((current) => {
      if (!current.data) return current
      const remaining = (current.data.extension_requests ?? []).filter(
        (item) => item.id !== booking.id || item.extension_end !== booking.extension_end,
      )
      return { ...current, data: { ...current.data, extension_requests: remaining } }
    })
    load()
  }

  const counts = statusCounts(resources ?? [])
  const decisions = overview ? todoCards(overview).filter((card) => MANAGER_DECIDES.includes(card.key)) : []
  const totals = usage?.totals
  const mostBooked = usage ? busiest(usage.results) : []

  return (
    <section className="today manager-home">
      <PageHeader title="Lab overview" description="Everything a Manager looks after, on one page."
        actions={<RefreshStamp at={overviewSection.updatedAt} onRefresh={load}
          busy={overviewSection.loading || resourcesSection.loading || usageSection.loading}
          emptyText={overviewSection.error ? 'Overview unavailable' : undefined} />} />
      <h2 className="manager-home-heading">Only a Manager decides</h2>
      <SectionStatus section={overviewSection} name="manager approvals" onRetry={reloadOverview} />
      {overview && (
        <>
          {/* 2026-11-09 (Loy feedback): one row of small counts instead of a wall of big cards that are mostly 0. */}
          {decisions.every((card) => card.count === 0) && <p className="mh-clear">Nothing is waiting for your decision.</p>}
          <div className="mh-chips">
            {decisions.map((card) => (
              <Link key={card.key} to={card.to} className={`mh-chip is-${card.tone}`}>
                <strong>{card.count}</strong> {card.label}
              </Link>
            ))}
            <Link to="/admin/today" className="mh-chip is-grey mh-chip-admin">
              <strong>{overview.pending_bookings + overview.pending_inductions}</strong> Requests and inductions for Admins →
            </Link>
          </div>
        </>
      )}

      <div className="today-grid">
        {hasRequests && (
          <article className="today-panel is-wide">
            <h2 className="mh-extensions-heading" tabIndex={-1} ref={requestsHeading}>Extension requests</h2>
            <p className="bk-muted">People in the lab now who ask to finish later. Approving moves the end if the time after is still free.</p>
            <ul className="today-list">
              {extensionRequests.map((booking) => (
                <ExtensionRow key={`${booking.id}:${booking.extension_end}`} booking={booking}
                  resourceName={resources?.find((item) => item.id === booking.resource_id)?.name ?? 'Resource'}
                  onDecided={() => extensionDecided(booking)} />
              ))}
            </ul>
          </article>
        )}
        <article className="today-panel">
          <h2>Rooms and equipment</h2>
          <SectionStatus section={resourcesSection} name="rooms and equipment" onRetry={reloadResources} />
          {resources && <SplitBar parts={[
            { label: 'open', count: counts.AVAILABLE, color: 'var(--green)' },
            { label: 'under maintenance', count: counts.MAINTENANCE, color: 'var(--amber)' },
            { label: 'closed', count: counts.CLOSED, color: 'var(--red)' },
          ]} empty="No rooms or equipment yet." />}
          {overview && overview.out_of_service.length > 0 && (
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
          <SectionStatus section={usageSection} name="weekly usage" onRetry={reloadUsage} />
          {totals && (
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
          )}
          <p>{overview && <>{overview.today_count} booking{overview.today_count === 1 ? '' : 's'} today · </>}
            <Link to="/admin/records?tab=usage">Usage statistics</Link>
          </p>
        </article>

        <article className="today-panel">
          <h2>Booking history</h2>
          <p className="bk-muted">Every booking of one person over the last year. Only Managers see the full history.</p>
          <form className="ui-filters" onSubmit={lookUp}>
            <label htmlFor="manager-history-zid">zID</label>
            <input id="manager-history-zid" ref={zidInput} name="zid" autoComplete="off" spellCheck={false}
              aria-invalid={zidError ? true : undefined} aria-describedby={zidError ? 'manager-history-zid-error' : undefined}
              placeholder="e.g. z5123456" maxLength={8} value={zid}
              onChange={(e) => { setZid(e.target.value); setZidError('') }} />
            <button type="submit" className="ui-btn ui-btn-ghost">Look up</button>
          </form>
          {zidError && <p id="manager-history-zid-error" className="bk-error" role="alert">{zidError}</p>}
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
    </section>
  )
}

type SectionState<T> = { data: T | null; error: string; loading: boolean; updatedAt: number | null }

// Sprint 3: approvals, resource status and usage each keep their last successful results.
function useSection<T>(fetchSection: () => Promise<T>) {
  const [section, setSection] = useState<SectionState<T>>({ data: null, error: '', loading: true, updatedAt: null })
  const generation = useRef(0)
  const reload = useCallback(async () => {
    // A manual refresh or approval can start a new load while an older one is in flight.
    const request = ++generation.current
    setSection((current) => ({ ...current, loading: true }))
    try {
      const data = await fetchSection()
      if (request === generation.current) setSection({ data, error: '', loading: false, updatedAt: Date.now() })
    } catch (e) {
      if (request === generation.current) setSection((current) => ({ ...current, error: errorMessage(e), loading: false }))
    }
  }, [fetchSection])
  return [section, reload, setSection] as const
}

async function loadResourceList() {
  return (await listResources({})).results
}

function loadWeeklyUsage() {
  const week = currentWeek(todaySydney())
  return getUsageReport(week.first, week.last)
}

function SectionStatus({ section, name, onRetry }: { section: SectionState<unknown>; name: string; onRetry: () => void }) {
  if (section.error) {
    return (
      <div className="mh-section-status">
        <p className="bk-error" role="alert">
          {section.data ? `Could not refresh ${name}.` : `Could not load ${name}.`} {section.error}
          {section.data !== null && ' Showing the previous results.'}
        </p>
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onRetry} disabled={section.loading}>
          {section.loading ? 'Retrying…' : 'Try again'}
        </button>
      </div>
    )
  }
  return section.loading && section.data === null ? <p className="mh-section-status" role="status">Loading {name}…</p> : null
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
  const feedback = useFeedback()
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function decide(decision: 'APPROVED' | 'REJECTED') {
    if (!booking.extension_end) return
    setBusy(true)
    setError('')
    try {
      const updated = await reviewExtension(booking.id, decision, booking.extension_end, reason.trim())
      onDecided()
      if (decision === 'APPROVED') feedback.success(`${resourceName} is booked until ${fmtTime(updated.end)}.`, 'Extension approved')
      else feedback.success('The requester can see your reason.', 'Extension rejected')
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
