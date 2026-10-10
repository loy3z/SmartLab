import { useEffect, useState } from 'react'
import { getDashboard, listRequirements, listResources } from '../booking/api'
import { errorMessage, fmtDateTime, fmtTime, STATUS_TEXT, TZ } from '../booking/format'
import { AlertIcon, CalendarIcon, CapIcon, CheckIcon, ClockIcon, DoorIcon } from '../booking/icons'
import type { Dashboard, Qualification, Requirement, Resource, User } from '../booking/types'
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

const qualificationLabels = {
  VERIFIED: 'Verified',
  PENDING: 'Under review',
  REJECTED: 'Resubmit required',
  EXPIRED: 'Expired',
  NOT_SUBMITTED: 'Not submitted',
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
  const firstName = user.display_name.trim().split(/\s+/)[0] || 'there'

  return (
    <div className="dash-page">
      <header className="dash-header">
        <div>
          <p className="dash-eyebrow">YOUR STUDENT DASHBOARD</p>
          <h1>Welcome back, {firstName}.</h1>
          <p className="dash-intro">Your spaces, bookings and induction progress, all in one place.</p>
        </div>
        <a className="dash-primary" href="#/resources"><CalendarIcon /> Book a resource</a>
      </header>

      <div className="dash-toolbar">
        <span>{state.status === 'ready' ? `Updated ${fmtTime(new Date(state.loadedAt).toISOString())} · Sydney time` : 'Your booking overview'}</span>
        <button className="dash-text-button" onClick={refresh} disabled={state.status === 'loading'}>
          {state.status === 'loading' ? 'Refreshing…' : 'Refresh overview'}
        </button>
      </div>

      {state.status === 'loading' && (
        <div className="dash-loading" role="status">
          <span className="dash-loading-dot" aria-hidden="true" /> Loading your dashboard…
        </div>
      )}

      {state.status === 'error' && (
        <div className="dash-error" role="alert">
          <AlertIcon size={28} />
          <div><h2>We couldn’t load your dashboard</h2><p>{state.message}</p></div>
          <button className="dash-secondary" onClick={refresh}>Try again</button>
        </div>
      )}

      {state.status === 'ready' && <DashboardContent state={state} />}
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
    ? upcoming.slice(0, 4)
    : [...data.bookings].sort((first, second) => Date.parse(second.created_at) - Date.parse(first.created_at)).slice(0, 4)

  const requirementById = new Map(requirements.map((requirement) => [requirement.id, requirement]))
  // Preserve known submissions even if their requirement is no longer returned by the catalogue.
  for (const qualification of qualifications.values()) {
    if (!requirementById.has(qualification.requirement_id)) {
      requirementById.set(qualification.requirement_id, {
        id: qualification.requirement_id,
        name: qualification.title || 'Induction submission',
        description: '',
      })
    }
  }

  return (
    <>
      {warnings.length > 0 && <p className="dash-warning" role="status"><AlertIcon /> {warnings.join(' ')} Use Refresh overview to try again.</p>}

      <section className="dash-stats" aria-label="Booking and induction summary">
        <a className="dash-stat" href="#/bookings">
          <span className="dash-stat-icon"><CalendarIcon size={24} /></span>
          <span className="dash-stat-label">Upcoming bookings</span>
          <strong>{upcoming.length}</strong>
          <span className="dash-stat-detail">Approved and ready to go</span>
        </a>
        <a className="dash-stat" href="#/bookings">
          <span className="dash-stat-icon dash-stat-icon-amber"><ClockIcon size={24} /></span>
          <span className="dash-stat-label">Pending requests</span>
          <strong>{pendingCount}</strong>
          <span className="dash-stat-detail">Awaiting checks, approval or a place</span>
        </a>
        <a className="dash-stat" href="#/induction">
          <span className="dash-stat-icon dash-stat-icon-green"><CheckIcon size={24} /></span>
          <span className="dash-stat-label">Verified inductions</span>
          <strong>{verifiedCount}</strong>
          <span className="dash-stat-detail">Current, valid training records</span>
        </a>
      </section>

      <div className="dash-columns">
        <section className="dash-panel" aria-labelledby="dash-bookings-title">
          <header className="dash-panel-header">
            <div><h2 id="dash-bookings-title">{upcoming.length ? 'Coming up next' : 'Recent requests'}</h2><p>All booking times are shown in Sydney time.</p></div>
            <a className="dash-link" href="#/bookings">View all bookings <span aria-hidden="true">↗</span></a>
          </header>
          {displayedBookings.length === 0 ? (
            <div className="dash-empty">
              <span className="dash-empty-icon"><CalendarIcon size={32} /></span>
              <h3>Your next booking starts here</h3>
              <p>Find a room or equipment for your next session.</p>
              <a className="dash-secondary" href="#/resources">Browse resources</a>
            </div>
          ) : (
            <ul className="dash-booking-list">
              {displayedBookings.map((booking) => {
                const resource = resourceById.get(booking.resource_id)
                const start = new Date(booking.start)
                return (
                  <li className="dash-booking" key={booking.id}>
                    <div className="dash-date" aria-hidden="true"><span>{monthFormat.format(start)}</span><strong>{dayFormat.format(start)}</strong></div>
                    <div className="dash-booking-info">
                      <h3>{resource?.name ?? `Resource ${booking.resource_id.slice(-6)}`}</h3>
                      <p><time dateTime={booking.start}>{fmtDateTime(booking.start)}</time> – <time dateTime={booking.end}>{fmtDateTime(booking.end)}</time></p>
                      {resource?.location && <span className="dash-location">{resource.location}</span>}
                      <span className={`dash-badge dash-booking-status-${booking.status}`}>{STATUS_TEXT[booking.status]}</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section className="dash-panel" aria-labelledby="dash-induction-title">
          <header className="dash-panel-header">
            <div><h2 id="dash-induction-title">Induction & training</h2><p>Check your eligibility before booking.</p></div>
            <CapIcon size={25} />
          </header>
          {requirementById.size === 0 ? (
            <div className="dash-empty dash-empty-compact">
              <CapIcon size={32} />
              <p>{warnings.length ? 'Visit Induction & Training to check available requirements.' : 'No induction requirements are available yet.'}</p>
            </div>
          ) : (
            <ul className="dash-induction-list">
              {[...requirementById.values()].slice(0, 4).map((requirement) => {
                const qualification = qualifications.get(requirement.id)
                const status = qualification?.effective_status ?? 'NOT_SUBMITTED'
                return (
                  <li key={requirement.id}>
                    <span className={`dash-induction-icon ${status === 'VERIFIED' ? 'is-verified' : ''}`}>
                      {status === 'VERIFIED' ? <CheckIcon /> : <CapIcon />}
                    </span>
                    <div>
                      <h3>{requirement.name}</h3>
                      <span className={`dash-badge dash-qualification-status-${status}`}>{qualificationLabels[status]}</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          <footer className="dash-panel-footer"><a className="dash-link" href="#/induction">Manage induction & training <span aria-hidden="true">→</span></a></footer>
        </section>
      </div>

      <aside className="dash-tip">
        <span className="dash-tip-icon"><DoorIcon size={28} /></span>
        <div><h2>A space for your next idea</h2><p>Explore shared labs, rooms and equipment. Check availability and submit your next request.</p></div>
        <a className="dash-link" href="#/resources">Explore resources <span aria-hidden="true">→</span></a>
      </aside>
    </>
  )
}
