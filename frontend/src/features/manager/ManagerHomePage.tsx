// 2026-11-07 (client, Week 8): the Manager home page. Admins land on Today (the review queue); a Manager lands here and
// sees the whole lab: what only a Manager decides, rooms and equipment, this week's use, and the booking history lookup.
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { PageHeader, RefreshStamp } from '../../ui/components'
import { getStaffOverview, getUsageReport, listResources, reviewExtension } from '../../api/index.ts'
import { errorMessage, fmtTime, todaySydney } from '../booking/format'
import type { Booking, Resource, StaffOverview, UsageReport } from '../../api/types/index.ts'
import { MANAGER_DECIDES, todoCards } from '../admin/today'
import { percent } from './usage'
import { cleanZid, currentWeek, statusCounts } from './manager-home'

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

  function lookUp(event: FormEvent) {
    event.preventDefault()
    const clean = cleanZid(zid)
    if (!clean) return setZidError('Enter a zID: z followed by 7 digits, e.g. z5123456.')
    navigate(`/admin/records?q=${clean}`)
  }

  const counts = statusCounts(resources)
  const decisions = overview ? todoCards(overview).filter((card) => MANAGER_DECIDES.includes(card.key)) : []
  const totals = usage?.totals

  return (
    <section className="today manager-home">
      <PageHeader title="Lab overview" description="Everything a Manager looks after, on one page."
        actions={<RefreshStamp at={loadedAt} onRefresh={() => void load()} busy={loading && loadedAt !== null} />} />
      {error && <p className="bk-error" role="alert">{error}</p>}
      {!overview && loading && <p role="status">Loading…</p>}
      {overview && (
        <>
          <h2 className="manager-home-heading">Only a Manager decides</h2>
          <div className="today-cards">
            {decisions.map((card) => (
              <Link key={card.key} to={card.to} className={`today-card is-${card.tone}`}>
                <span className="today-count">{card.count}</span>
                <span className="today-label">{card.label}</span>
              </Link>
            ))}
            <Link to="/admin/today" className="today-card is-grey">
              <span className="today-count">{overview.pending_bookings + overview.pending_inductions}</span>
              <span className="today-label">Requests and inductions for Admins</span>
              <small>Open Today to review them too</small>
            </Link>
          </div>

          <div className="today-grid">
            {(overview.extension_requests ?? []).length > 0 && (
              <article className="today-panel is-wide">
                <h2>Extension requests</h2>
                <p className="bk-muted">People in the lab now who ask to finish later. Approving moves the end if the time after is still free.</p>
                <ul className="today-list">
                  {(overview.extension_requests ?? []).map((booking) => (
                    <ExtensionRow key={booking.id} booking={booking}
                      resourceName={resources.find((item) => item.id === booking.resource_id)?.name ?? 'Resource'} onDecided={() => void load()} />
                  ))}
                </ul>
              </article>
            )}
            <article className="today-panel">
              <h2>Rooms and equipment</h2>
              <p className="manager-home-figures">
                <span><strong>{counts.AVAILABLE}</strong> open</span>
                <span><strong>{counts.MAINTENANCE}</strong> under maintenance</span>
                <span><strong>{counts.CLOSED}</strong> closed</span>
              </p>
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
                <p className="manager-home-figures">
                  <span><strong>{totals.booked_hours}</strong> h booked</span>
                  <span><strong>{percent(totals.utilisation)}</strong> of opening hours</span>
                  <span><strong>{percent(totals.attendance_rate)}</strong> checked in</span>
                  <span><strong>{totals.no_show}</strong> missed</span>
                </p>
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

/** 2026-11-07: one extension request with Approve, or Reject with a reason (shown to the person). */
function ExtensionRow({ booking, resourceName, onDecided }: { booking: Booking; resourceName: string; onDecided: () => void }) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function decide(decision: 'APPROVED' | 'REJECTED') {
    setBusy(true)
    setError('')
    try {
      await reviewExtension(booking.id, decision, reason.trim())
      onDecided()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="manager-home-request">
      <span><strong>{resourceName}</strong> · {booking.booked_for?.display_name ?? 'Someone'}
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
