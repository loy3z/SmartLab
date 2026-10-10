import { useEffect, useMemo, useState } from 'react'
import { BookingForm } from './BookingForm'
import { demoLogin, getMe, getToken, listQualifications, listRequirements, listResources, setToken } from './api'
import { errorMessage } from './format'
import { AlertIcon, CheckIcon, DoorIcon, FlaskIcon, SearchIcon, UploadIcon } from './icons'
import { Layout, type Page } from './Layout'
import { Modal } from './Modal'
import { MyBookings } from './MyBookings'
import { ResourceCard, type InductionState } from './ResourceCard'
import { InductionPage } from '../induction/InductionPage'
import type { Qualification, Requirement, Resource, User } from './types'
import { QualificationReviewPage } from '../admin/QualificationReviewPage'
import { ManagerBookingsPage } from '../manager/ManagerBookingsPage'
import './booking.css'

/** Dev-only login so this feature works before frontend A's login lands. */
function DevLogin({ onDone }: { onDone: () => void }) {
  const [zid, setZid] = useState('z1000001')
  const [error, setError] = useState('')
  return (
    <div className="bk-login">
      <div className="bk-panel">
        <h2>SmartLab Booking</h2>
        <p className="bk-muted">Dev login (demo mode only; replaced by the real login page).</p>
        <input value={zid} onChange={(e) => setZid(e.target.value)} />
        <button
          className="bk-btn-yellow"
          onClick={async () => {
            try {
              setToken((await demoLogin(zid)).access_token)
              onDone()
            } catch (e) {
              setError(errorMessage(e))
            }
          }}
        >
          Login
        </button>
        {error && <p className="bk-error">{error}</p>}
      </div>
    </div>
  )
}

function stateFor(r: Resource, quals: Qualification[]): InductionState {
  if (!r.required_qualification_id) return 'NOT_CONFIGURED'
  const latest = quals
    .filter((q) => q.requirement_id === r.required_qualification_id)
    .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))[0]
  return latest ? latest.effective_status : 'NOT_SUBMITTED'
}

function Browse({ onBooked }: { onBooked: () => void }) {
  const [kind, setKind] = useState('')
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [resources, setResources] = useState<Resource[]>([])
  const [reqs, setReqs] = useState<Requirement[]>([])
  const [quals, setQuals] = useState<Qualification[]>([])
  const [error, setError] = useState('')
  const [open, setOpen] = useState<Resource | null>(null)

  useEffect(() => {
    Promise.all([listRequirements(), listQualifications()])
      .then(([r, qs]) => (setReqs(r.results), setQuals(qs.results)))
      .catch((e) => setError(errorMessage(e)))
  }, [open])

  useEffect(() => {
    listResources({ kind, q: term })
      .then((r) => (setResources(r.results.filter((x) => x.active)), setError('')))
      .catch((e) => setError(errorMessage(e)))
  }, [kind, term])

  // One banner per induction requirement that active resources need.
  const banners = useMemo(
    () =>
      reqs
        .map((req) => {
          const rs = resources.filter((r) => r.required_qualification_id === req.id)
          const kinds = new Set(rs.map((r) => r.kind))
          const latest = quals
            .filter((x) => x.requirement_id === req.id)
            .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))[0]
          return { req, kinds, state: latest ? latest.effective_status : 'NOT_SUBMITTED', used: rs.length > 0 }
        })
        .filter((b) => b.used),
    [reqs, resources, quals],
  )

  return (
    <>
      <h1>Book a resource</h1>
      <p className="bk-sub">Browse resources. Submit induction before requesting a booking.</p>

      <div className="bk-banners">
        {banners.map(({ req, kinds, state }) => {
          const ok = state === 'VERIFIED'
          return (
            <div key={req.id} className={`bk-banner ${ok ? 'is-ok' : 'is-warn'}`}>
              <span className="bk-banner-icon">{kinds.has('EQUIPMENT') && !kinds.has('ROOM') ? <FlaskIcon size={34} /> : <DoorIcon size={34} />}</span>
              <div className="bk-banner-text">
                <div>
                  <b>{req.name}</b>
                  <span className={`bk-chip ${ok ? 'is-ok' : 'is-warn'}`}>
                    {ok ? <CheckIcon size={16} /> : <AlertIcon size={16} />}
                    {ok ? 'Verified' : state === 'PENDING' ? 'Pending' : state === 'NOT_SUBMITTED' ? 'Not submitted' : state === 'REJECTED' ? 'Rejected' : 'Expired'}
                  </span>
                </div>
                <small>{req.description || 'Required before requesting a booking.'}</small>
              </div>
              {!ok && state !== 'PENDING' && (
                <button className="bk-btn-yellow" disabled title="Available on the Induction page">
                  <UploadIcon size={18} /> Upload induction
                </button>
              )}
            </div>
          )
        })}
      </div>

      <form
        className="bk-search"
        onSubmit={(e) => {
          e.preventDefault()
          setTerm(q)
        }}
      >
        <SearchIcon />
        <input placeholder="Search rooms or equipment…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="bk-btn-yellow" type="submit">Search</button>
      </form>

      <div className="bk-pills">
        {[['', 'All resources'], ['ROOM', 'Rooms'], ['EQUIPMENT', 'Equipment']].map(([k, label]) => (
          <button key={k} className={`bk-pill ${kind === k ? 'is-on' : ''}`} onClick={() => setKind(k)}>
            {label}
          </button>
        ))}
      </div>

      <h2 className="bk-h2">Resources <small>{resources.length} resources</small></h2>
      {error && <p className="bk-error">{error}</p>}
      <div className="bk-grid">
        {resources.map((r) => (
          <ResourceCard key={r.id} resource={r} state={stateFor(r, quals)} onOpen={() => setOpen(r)} />
        ))}
      </div>
      {resources.length === 0 && !error && <p className="bk-muted">No resources found.</p>}

      {open && (
        <Modal onClose={() => setOpen(null)}>
          <BookingForm resource={open} onBooked={onBooked} />
        </Modal>
      )}
    </>
  )
}

export function BookingApp() {
  const [authed, setAuthed] = useState(!!getToken())
  const [page, setPage] = useState<Page>('browse')
  const [user, setUser] = useState<User | null>(null)
  const [bump, setBump] = useState(0)

  useEffect(() => {
    if (!authed) return

    let active = true

    getMe()
      .then((currentUser) => {
        if (!active) return

        setUser(currentUser)

        const staff =
          currentUser.role === 'ADMIN' ||
          currentUser.role === 'MANAGER'

        setPage(staff ? 'qualification-review' : 'browse')
      })
      .catch(() => {
        if (!active) return

        setToken(null)
        setUser(null)
        setAuthed(false)
      })

    return () => {
      active = false
    }
  }, [authed])

  if (!authed) {
    return <DevLogin onDone={() => setAuthed(true)} />
  }

  if (!user) {
    return <p>Loading your account...</p>
  }

  const isStaff = user.role === 'ADMIN' || user.role === 'MANAGER'

  function handleSignOut() {
    setToken(null)
    setUser(null)
    setPage('browse')
    setAuthed(false)
  }

  return (
    <Layout
      page={page}
      onNavigate={setPage}
      user={user}
      onSignOut={handleSignOut}
    >
      {page === 'browse' && (
        <Browse onBooked={() => setBump((n) => n + 1)} />
      )}

      {page === 'mine' && (
        <MyBookings refreshKey={bump} />
      )}

      {page === 'induction' && (
        <InductionPage />
      )}

      {page === 'qualification-review' && isStaff && (
        <QualificationReviewPage />
      )}
      {page === 'manager-bookings' && user?.role === 'MANAGER' && (
        <ManagerBookingsPage />
      )}
    </Layout>
  )
}