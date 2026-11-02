import { AnnouncementBoard } from '../announcements/AnnouncementBoard' // Sprint 3 (1.19.0)
import { useAnnouncements } from '../announcements/use-announcements' // Sprint 3 (fluency V5)
// Sprint 3 (1.16.0): "Today" — the Admin and Manager home page: what needs doing first, each card linking to its page.
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { PageHeader, RefreshStamp } from '../../ui/components'
import { getStaffOverview, listResources } from '../../api/index.ts'
import { errorMessage, fmtRelative, fmtTime } from '../booking/format'
import type { Booking, Resource, StaffOverview } from '../../api/types/index.ts'
import { attendanceLabel, todoCards } from './today'
import { CheckIcon } from '../booking/icons'

export function TodayPage() {
  const announcements = useAnnouncements()
  const [data, setData] = useState<StaffOverview | null>(null)
  const [names, setNames] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [overview, resources] = await Promise.all([getStaffOverview(), listResources({})])
      setData(overview)
      setNames(Object.fromEntries(resources.results.map((item: Resource) => [item.id, item.name])))
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

  const now = loadedAt ?? 0
  const who = (b: Booking) => b.booked_for?.display_name ?? 'Someone'
  const today = new Intl.DateTimeFormat('en-AU', { timeZone: 'Australia/Sydney', weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())
  // Sprint 3 (fluency V5): gate only the first paint; retain the existing refresh behavior once data exists.
  const homeReady = announcements.settled && (data !== null || !loading)
  const waiting = data !== null && todoCards(data).some(card => card.count > 0)

  return (
    <section className="today">
      <PageHeader title="Today" description={today}
        actions={<RefreshStamp at={loadedAt} onRefresh={() => void load()} busy={(loading || !announcements.settled) && loadedAt !== null} />} />
      {/* Sprint 3 (1.19.0): public notices are independent of personal notifications. */}
      {homeReady && <AnnouncementBoard announcements={announcements} />}
      {error && <p className="bk-error" role="alert">{error}</p>}
      {(!data && loading || !announcements.settled) && <p role="status">Loading…</p>}
      {homeReady && data && (
        <>
          {/* Sprint 3 (internal-tool UI, AI-2): a plain status line instead of a slogan. */}
          <div className="today-brief">
            <div><h2>{waiting ? 'Waiting for review' : 'Nothing waiting for review'}</h2></div>
            {/* Sprint 3 (2026-10-28 feedback L2): the check only means "all clear". */}
            {!waiting && <span className="today-brief-mark"><CheckIcon size={23} /></span>}
          </div>
          <div className="today-cards">
            {todoCards(data).filter(card => card.count > 0).map((card) => (
              <Link key={card.key} to={card.to} className={`today-card is-${card.tone}`}>
                <span className="today-count">{card.count}</span>
                <span className="today-label">{card.label}</span>
                {card.hint && <small>{card.hint}</small>}
              </Link>
            ))}
          </div>

          <div className="today-grid">
            {/* Sprint 3 (2026-10-28 feedback L2): a panel without its neighbour takes the whole row. */}
            {data.due_soon.length > 0 && <article className={`today-panel${data.out_of_service.length ? '' : ' is-wide'}`}>
              <h2>Decide soon</h2>
              <p className="bk-muted">Review deadlines within {data.due_soon_hours} hours. Long bookings expire without a Manager's decision; ordinary requests follow the automatic review rules.</p>
              {data.due_soon.length === 0 ? <p className="today-empty">Nothing is close to its deadline.</p> : (
                <ul className="today-list">
                  {data.due_soon.map((b) => (
                    <li key={b.id}>
                      <Link to="/admin/bookings">
                        <strong>{names[b.resource_id] ?? 'Resource'}</strong> · {who(b)}
                        {b.long_booking && <span className="ui-pill is-amber">Longer booking · Manager approval</span>}
                        <span className="today-meta">{fmtTime(b.start)}, {new Date(b.start).toLocaleDateString('en-AU', { timeZone: 'Australia/Sydney', day: 'numeric', month: 'short' })}</span>
                        {b.review_due_at && <span className="today-due">decide {fmtRelative(b.review_due_at, now)}</span>}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </article>}

            {data.out_of_service.length > 0 && <article className={`today-panel${data.due_soon.length ? '' : ' is-wide'}`}>
              <h2>Out of service</h2>
              <p className="bk-muted">Rooms and equipment under maintenance or closed. People with bookings were notified; decide what happens to them.</p>
              {data.out_of_service.length === 0 ? <p className="today-empty">Everything is open.</p> : (
                <ul className="today-list">
                  {data.out_of_service.map(({ resource, affected_bookings }) => (
                    <li key={resource.id}>
                      <Link to="/manager/bookings">
                        <strong>{resource.name}</strong> · {resource.status === 'MAINTENANCE' ? 'Under maintenance' : 'Closed'}
                        {resource.status_reason && <span className="today-meta">{resource.status_reason}</span>}
                        <span className={affected_bookings ? 'today-due' : 'today-meta'}>{affected_bookings} future booking{affected_bookings === 1 ? '' : 's'}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </article>}

            <article className="today-panel is-wide">
              <h2>Bookings today <small>{data.today_count}{data.missed_today ? ` · ${data.missed_today} missed` : ''}</small></h2>
              {data.today.length === 0 ? <p className="today-empty">No approved bookings today.</p> : (
                <ol className="today-timeline">
                  {data.today.map((b) => (
                    <li key={b.id}>
                      <span className="today-time">{fmtTime(b.start)}–{fmtTime(b.end)}</span>
                      <span><strong>{names[b.resource_id] ?? 'Resource'}</strong> · {who(b)}</span>
                      <span className={`today-att is-${(b.attendance ?? 'none').toLowerCase()}`}>{attendanceLabel(b, now)}</span>
                    </li>
                  ))}
                </ol>
              )}
              {data.today_count > data.today.length && <Link to="/admin/records">All {data.today_count} in Booking records →</Link>}
            </article>
          </div>
        </>
      )}
    </section>
  )
}
