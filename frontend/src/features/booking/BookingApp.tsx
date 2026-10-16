import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { BookingForm } from './BookingForm'
import { listQualifications, listRequirements, listResources } from './api'
import { errorMessage } from './format'
import { AlertIcon, CheckIcon, DoorIcon, FlaskIcon, SearchIcon, UploadIcon } from './icons'
import { Modal } from './Modal'
import { ResourceCard, type InductionState } from './ResourceCard'
import type { Qualification, Requirement, Resource } from './types'

function latestStatus(requirementId: string, quals: Qualification[]) {
  const latest = quals
    .filter((q) => q.requirement_id === requirementId)
    .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))[0]
  return latest ? latest.effective_status : 'NOT_SUBMITTED'
}

/** Mirrors the backend: prerequisites (e.g. General before Advanced) first, then the resource's own induction. */
function stateFor(r: Resource, quals: Qualification[], reqs: Requirement[]): InductionState {
  if (!r.required_qualification_id) return 'NOT_CONFIGURED'
  const requirement = reqs.find((item) => item.id === r.required_qualification_id)
  if (requirement?.prerequisite_ids.some((id) => latestStatus(id, quals) !== 'VERIFIED')) return 'PREREQUISITE_REQUIRED'
  return latestStatus(r.required_qualification_id, quals)
}

function prerequisiteName(r: Resource, quals: Qualification[], reqs: Requirement[]): string | undefined {
  const requirement = reqs.find((item) => item.id === r.required_qualification_id)
  const missing = requirement?.prerequisite_ids.find((id) => latestStatus(id, quals) !== 'VERIFIED')
  return missing ? reqs.find((item) => item.id === missing)?.name : undefined
}

type View = 'ROOM' | 'EQUIPMENT'

/** Frontend B's resource page; authentication, routing and layout are owned by app/. */
export function BookingApp({ onBooked }: { onBooked: () => void }) {
  const [view, setView] = useState<View>('ROOM')
  const [roomFilter, setRoomFilter] = useState('')
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
    listResources({ q: term })
      .then((r) => (setResources(r.results.filter((x) => x.active)), setError('')))
      .catch((e) => setError(errorMessage(e)))
  }, [term])

  const rooms = resources.filter((r) => r.kind === 'ROOM')
  const equipment = resources.filter((r) => r.kind === 'EQUIPMENT')
  const roomName = (id: string | null) => (id ? rooms.find((room) => room.id === id)?.name : undefined)
  const shown = view === 'ROOM' ? rooms : equipment.filter((item) => !roomFilter || item.room_id === roomFilter)

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
          const missing = req.prerequisite_ids.find((id) => latestStatus(id, quals) !== 'VERIFIED')
          const lockedBy = missing ? reqs.find((item) => item.id === missing)?.name ?? 'the prerequisite induction' : null
          return { req, kinds, state: latest ? latest.effective_status : 'NOT_SUBMITTED', used: rs.length > 0, lockedBy }
        })
        .filter((b) => b.used),
    [reqs, resources, quals],
  )

  return (
    <>
      <h1>Book a resource</h1>
      <p className="bk-sub">Browse resources. Submit induction before requesting a booking.</p>

      <div className="bk-banners">
        {banners.map(({ req, kinds, state, lockedBy }) => {
          const ok = state === 'VERIFIED' && !lockedBy
          // Evidence for an advanced induction is accepted only after its prerequisite is verified.
          const locked = lockedBy !== null && state !== 'VERIFIED' && state !== 'PENDING'
          return (
            <div key={req.id} className={`bk-banner ${ok ? 'is-ok' : 'is-warn'}`}>
              <span className="bk-banner-icon">{kinds.has('EQUIPMENT') && !kinds.has('ROOM') ? <FlaskIcon size={34} /> : <DoorIcon size={34} />}</span>
              <div className="bk-banner-text">
                <div>
                  <b>{req.name}</b>
                  <span className={`bk-chip ${ok ? 'is-ok' : 'is-warn'}`}>
                    {ok ? <CheckIcon size={16} /> : <AlertIcon size={16} />}
                    {ok ? 'Verified' : locked ? 'Locked' : state === 'PENDING' ? 'Pending' : state === 'NOT_SUBMITTED' ? 'Not submitted' : state === 'REJECTED' ? 'Rejected' : 'Expired'}
                  </span>
                </div>
                <small>{req.description || 'Required before requesting a booking.'}</small>
                {locked && <small className="bk-banner-lock">Complete {lockedBy} first. You can upload this once it is verified.</small>}
                {lockedBy && !locked && <small className="bk-banner-lock">You also need a current {lockedBy} to book.</small>}
              </div>
              {state === 'PENDING' && <span className="bk-muted">Under review. You can book once it is verified.</span>}
              {!ok && !locked && state !== 'PENDING' && state !== 'VERIFIED' && (
                <Link className="bk-btn-yellow" to={`/induction?requirement=${req.id}`}>
                  <UploadIcon size={18} /> Upload induction
                </Link>
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

      <div className="bk-pills" role="tablist" aria-label="Resource type">
        {([['ROOM', 'Rooms', rooms.length], ['EQUIPMENT', 'Equipment', equipment.length]] as const).map(([key, label, count]) => (
          <button key={key} role="tab" aria-selected={view === key} className={`bk-pill ${view === key ? 'is-on' : ''}`}
            onClick={() => { setView(key); if (key === 'ROOM') setRoomFilter('') }}>
            {label} <span className="bk-pill-count">{count}</span>
          </button>
        ))}
        {view === 'EQUIPMENT' && (
          <select className="bk-room-filter" aria-label="Filter equipment by room" value={roomFilter} onChange={(e) => setRoomFilter(e.target.value)}>
            <option value="">All rooms</option>
            {rooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
          </select>
        )}
      </div>

      <h2 className="bk-h2">
        {view === 'ROOM' ? 'Rooms' : roomFilter ? `Equipment in ${roomName(roomFilter)}` : 'Equipment'}
        <small>{shown.length} {view === 'ROOM' ? (shown.length === 1 ? 'room' : 'rooms') : (shown.length === 1 ? 'device' : 'devices')}</small>
      </h2>
      {error && <p className="bk-error">{error}</p>}
      <div className="bk-grid">
        {shown.map((r) => (
          <ResourceCard
            key={r.id}
            resource={r}
            state={stateFor(r, quals, reqs)}
            prerequisiteName={prerequisiteName(r, quals, reqs)}
            onOpen={() => setOpen(r)}
            roomName={r.kind === 'EQUIPMENT' ? roomName(r.room_id) : undefined}
            equipmentCount={r.kind === 'ROOM' ? equipment.filter((item) => item.room_id === r.id).length : undefined}
            onShowEquipment={r.kind === 'ROOM' ? () => { setView('EQUIPMENT'); setRoomFilter(r.id) } : undefined}
          />
        ))}
      </div>
      {shown.length === 0 && !error && <p className="bk-muted">{term ? 'Nothing matches your search.' : 'Nothing to show here yet.'}</p>}

      {open && (
        <Modal onClose={() => setOpen(null)}>
          <BookingForm resource={open} onBooked={onBooked} />
        </Modal>
      )}
    </>
  )
}
