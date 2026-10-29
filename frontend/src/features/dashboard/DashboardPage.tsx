import { AnnouncementBoard } from '../announcements/AnnouncementBoard' // Sprint 3 (1.19.0)
import { useAnnouncements } from '../announcements/use-announcements' // Sprint 3 (fluency V5)
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getDashboard, listRequirements, listResources } from '../../api/index.ts'
import { errorMessage, fmtDateTime, fmtRange, fmtTime, STATUS_TEXT, TZ } from '../booking/format'
import { AlertIcon, CalendarIcon, CapIcon, CheckIcon, ClockIcon } from '../booking/icons'
import type { Dashboard, Qualification, Requirement, Resource, User } from '../../api/types/index.ts'
import { InductionRow } from '../induction/InductionRow'
import { blockingPrerequisite } from '../induction/status'
import './dashboard.css'

type DashboardState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | {
      status: 'ready'
      data: Dashboard
      resources: Resource[]
      requirements: Requirement[]
      warnings: string[]
      loadedAt: number
    }


const dayFormat = new Intl.DateTimeFormat('en-AU', { day: 'numeric', timeZone: TZ })
const monthFormat = new Intl.DateTimeFormat('en-AU', { month: 'short', timeZone: TZ })

/** The backend evaluates eligibility from the latest submission, not any historical approval. */
function latestQualifications(qualifications: Qualification[]) {
  const latest = new Map<string, Qualification>()
  for (const qualification of qualifications) {
    const previous = latest.get(qualification.requirement_id)
    if (!previous || Date.parse(qualification.submitted_at) >= Date.parse(previous.submitted_at)) {
      latest.set(qualification.requirement_id, qualification)
    }
  }
  return latest
}

export function DashboardPage({ user }: { user: User }) {
  return <DashboardSession key={user.id} user={user} />
}

function DashboardSession({ user }: { user: User }) {
  const announcements = useAnnouncements()
  const [state, setState] = useState<DashboardState>({ status: 'loading' })
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true
    async function load() {
      const [dashboard, resources, requirements] = await Promise.allSettled([
        getDashboard(),
        listResources({}),
        listRequirements(),
      ])
      if (!active) return
      if (dashboard.status === 'rejected') {
        setState({ status: 'error', message: errorMessage(dashboard.reason) })
        return
      }

      const warnings: string[] = []
      if (resources.status === 'rejected') warnings.push('Resource names could not be loaded.')
      if (requirements.status === 'rejected') warnings.push('The full induction requirements list could not be loaded.')
      setState({
        status: 'ready',
        data: dashboard.value,
        resources: resources.status === 'fulfilled' ? resources.value.results : [],
        requirements: requirements.status === 'fulfilled' ? requirements.value.results : [],
        warnings,
        loadedAt: Date.now(),
      })
    }

    void load()
    return () => { active = false }
  }, [user.id, refreshKey])

  const refresh = () => {
    setState({ status: 'loading' })
    setRefreshKey((value) => value + 1)
  }
  // Sprint 3 (fluency V5): publish the first home and announcement result together; errors also settle.
  const loading = state.status === 'loading' || !announcements.settled
  // Only the first paint waits; "Refresh overview" reloads the overview and the announcements stay in place.
  const showAnnouncements = announcements.settled && (refreshKey > 0 || state.status !== 'loading')
  return (
    <div className="dash-page">
      {/* Sprint 3 (internal-tool UI, AI-2 / D5): the page is named like its menu item; no greeting, dateline or slogan. */}
      <header className="dash-header">
        <div>
          <h1>Dashboard</h1>
        </div>
        <Link className="dash-primary" to="/resources"><CalendarIcon /> Book a resource</Link>
      </header>

      {/* Sprint 3 (1.19.0): the same active announcements as the staff home page. */}
      {showAnnouncements && <AnnouncementBoard announcements={announcements} />}
      <div className="dash-toolbar">
        <span>{state.status === 'ready' && !loading ? `Updated ${fmtTime(new Date(state.loadedAt).toISOString())} · Sydney time` : 'Your booking overview'}</span>
        <button className="dash-text-button" onClick={refresh} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh overview'}
        </button>
      </div>

      {loading && (
        <div className="dash-loading" role="status">
          <span className="dash-loading-dot" aria-hidden="true" /> Loading your dashboard…
        </div>
      )}

      {!loading && state.status === 'error' && (
        <div className="dash-error" role="alert">
          <AlertIcon size={28} />
          <div><h2>We couldn’t load your dashboard</h2><p>{state.message}</p></div>
          <button className="dash-secondary" onClick={refresh}>Try again</button>
        </div>
      )}

      {!loading && state.status === 'ready' && <DashboardContent state={state} />}
    </div>
  )
}

function DashboardContent({ state }: { state: Extract<DashboardState, { status: 'ready' }> }) {
  const { data, resources, requirements, loadedAt, warnings } = state
  const resourceById = new Map(resources.map((resource) => [resource.id, resource]))
  const qualifications = latestQualifications(data.qualifications)
  const verifiedCount = [...qualifications.values()].filter((item) => item.effective_status === 'VERIFIED').length
  const upcoming = data.bookings
    .filter((booking) => booking.status === 'APPROVED' && Date.parse(booking.start) > loadedAt)
    .sort((first, second) => Date.parse(first.start) - Date.parse(second.start))
  const pendingCount = data.counts.WAITING_QUALIFICATION + data.counts.PENDING_APPROVAL + data.counts.WAITLISTED
  const displayedBookings = upcoming.length
    ? upcoming.slice(1, 4)
    : [...data.bookings].sort((first, second) => Date.parse(second.created_at) - Date.parse(first.created_at)).slice(0, 4)
  const nextBooking = upcoming[0]
  const nextResource = nextBooking ? resourceById.get(nextBooking.resource_id) : null

  const requirementById = new Map(requirements.map((requirement) => [requirement.id, requirement]))
  // Preserve known submissions even if their requirement is no longer returned by the catalogue.
  for (const qualification of qualifications.values()) {
    if (!requirementById.has(qualification.requirement_id)) {
      requirementById.set(qualification.requirement_id, {
        id: qualification.requirement_id,
        name: qualification.title || 'Induction submission',
        description: '',
        prerequisite_ids: [],
      })
    }
  }

  return (
    <>
      {warnings.length > 0 && <p className="dash-warning" role="status"><AlertIcon /> {warnings.join(' ')} Use Refresh overview to try again.</p>}

      {/* Sprint 3 (workspace UI): each count opens My Bookings on the matching tab (?view=). */}
      <section className="dash-stats" aria-label="Booking and induction summary">
        <Link className="dash-stat" to="/bookings?view=upcoming">
          <span className="dash-stat-icon"><CalendarIcon size={24} /></span>
          <span className="dash-stat-label">Upcoming bookings</span>
          <strong>{upcoming.length}</strong>
          <span className="dash-stat-detail">Approved and ready to go</span>
        </Link>
        <Link className="dash-stat" to="/bookings?view=pending">
          <span className="dash-stat-icon dash-stat-icon-amber"><ClockIcon size={24} /></span>
          <span className="dash-stat-label">Pending requests</span>
          <strong>{pendingCount}</strong>
          <span className="dash-stat-detail">Awaiting checks, approval or a place</span>
        </Link>
        <Link className="dash-stat" to="/induction">
          <span className="dash-stat-icon dash-stat-icon-green"><CheckIcon size={24} /></span>
          <span className="dash-stat-label">Verified inductions</span>
          <strong>{verifiedCount}</strong>
          <span className="dash-stat-detail">Current, valid training records</span>
        </Link>
      </section>

      {/* Sprint 3 (1.20.0): keep the compact next session and booking list together, beside training. */}
      <div className="dash-columns">
        <div className="dash-booking-column">
          <section className="dash-session" aria-labelledby="dash-bookings-title">
            <div className="dash-session-top"><span>Next session</span>{nextBooking && <span className="dash-session-dot">Confirmed</span>}</div>
            {nextBooking ? <>
              <h2 id="dash-bookings-title">{nextResource?.name ?? 'Your next booking'}</h2>
              <p className="dash-session-time"><CalendarIcon size={17} />{fmtRange(nextBooking.start, nextBooking.end)}</p>
              {nextResource?.location && <p className="dash-session-location">{nextResource.location}</p>}
              <footer className="dash-session-footer"><span>Times in Sydney</span><Link className="dash-session-link" to="/bookings">Manage booking <span aria-hidden="true">↗</span></Link></footer>
            </> : <>
              <h2 id="dash-bookings-title">No upcoming bookings</h2>{/* Sprint 3 (internal-tool UI, AI-2) */}
              <footer className="dash-session-footer"><span>Rooms &amp; equipment</span><Link className="dash-session-link" to="/resources">Browse resources <span aria-hidden="true">↗</span></Link></footer>
            </>}
          </section>

          {displayedBookings.length > 0 && <section className="dash-recent" aria-labelledby="dash-recent-title">
            <header className="dash-panel-header"><h2 id="dash-recent-title">{upcoming.length ? 'More upcoming' : 'Recent requests'}</h2><Link className="dash-link" to="/bookings">View all bookings <span aria-hidden="true">↗</span></Link></header>
            <ul className="dash-booking-list">{displayedBookings.map(booking => {
              const start = new Date(booking.start)
              return <li className="dash-booking" key={booking.id}>
                <div className="dash-date" aria-hidden="true"><span>{monthFormat.format(start)}</span><strong>{dayFormat.format(start)}</strong></div>
                <div className="dash-booking-info"><h3>{resourceById.get(booking.resource_id)?.name ?? 'Resource'}</h3><p>{fmtDateTime(booking.start)} – {fmtTime(booking.end)}</p></div>
                <span className={`dash-badge dash-booking-status-${booking.status}`}>{STATUS_TEXT[booking.status]}</span>
              </li>
            })}</ul>
          </section>}
        </div>

        <section className="dash-panel" aria-labelledby="dash-induction-title">
          <header className="dash-panel-header">
            <div><h2 id="dash-induction-title">Induction & training</h2></div>
            <CapIcon size={25} />
          </header>
          {requirementById.size === 0 ? (
            <div className="dash-empty dash-empty-compact">
              <CapIcon size={32} />
              <p>{warnings.length ? 'Visit Induction & training to check available requirements.' : 'No induction requirements are available yet.'}</p>
            </div>
          ) : (
            <ul className="ind-list dash-ind-list">
              {[...requirementById.values()].slice(0, 4).map((requirement) => (
                <li key={requirement.id}>
                  <InductionRow
                    requirement={requirement}
                    latest={qualifications.get(requirement.id)}
                    resources={resources}
                    linkTo={`/induction?requirement=${requirement.id}`}
                    blockedBy={blockingPrerequisite(requirement, qualifications, [...requirementById.values()])}
                  />
                </li>
              ))}
            </ul>
          )}
          <footer className="dash-panel-footer"><Link className="dash-link" to="/induction">Manage induction & training <span aria-hidden="true">→</span></Link></footer>
        </section>
      </div>
    </>
  )
}
