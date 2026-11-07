import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../auth/auth-context'
import { BookingForm } from './BookingForm'
import { AdditionalHoursForm } from './AdditionalHoursForm'
import { LongBookingForm } from './LongBookingForm'
import { FindTime } from './FindTime'
import { listQualifications, listRequirements, listResources } from '../../api/index.ts'
import { errorMessage, SEPARATE_BOOKING_TEXT } from './format' // Sprint 3 (1.16.0): SEPARATE_BOOKING_TEXT
import { AlertIcon, CheckIcon, SearchIcon, UploadIcon } from './icons'
import { Modal } from './Modal'
import { RecurringBookingForm } from './RecurringBookingForm' // Sprint 3
import { ResourceCard, type InductionState } from './ResourceCard'
import type { Qualification, Requirement, Resource } from '../../api/types/index.ts'

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
type Mode = 'browse' | 'find'
interface Picked { resource: Resource; start: string; minutes: number; date: string }

/** Frontend B's resource page; authentication, routing and layout are owned by app/. */
export function BookingApp({ onBooked }: { onBooked: () => void }) {
  const { user } = useAuth()
  const isStaff = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const [repeat, setRepeat] = useState<Resource | null>(null) // Sprint 3: weekly series dialog
  const [additional, setAdditional] = useState<Resource | null>(null)
  const [longBooking, setLongBooking] = useState<Resource | null>(null)
  const [view, setView] = useState<View>('ROOM')
  const [roomFilter, setRoomFilter] = useState('')
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [resources, setResources] = useState<Resource[]>([])
  const [reqs, setReqs] = useState<Requirement[]>([])
  const [quals, setQuals] = useState<Qualification[]>([])
  const [error, setError] = useState('')
  const [open, setOpen] = useState<Resource | null>(null)
  // "Find a free time" (day grid) or the original resource cards.
  const [mode, setMode] = useState<Mode>('browse')
  const [picked, setPicked] = useState<Picked | null>(null)
  const [people, setPeople] = useState('') // Sprint 3 (1.16.0): rooms that fit at least this many people

  useEffect(() => {
    Promise.all([listRequirements(), listQualifications()])
      .then(([r, qs]) => (setReqs(r.results), setQuals(qs.results)))
      .catch((e) => setError(errorMessage(e)))
  }, [open, picked])

  useEffect(() => {
    listResources({ q: term })
      .then((r) => (setResources(r.results.filter((x) => x.active)), setError('')))
      .catch((e) => setError(errorMessage(e)))
  }, [term])

  const rooms = resources.filter((r) => r.kind === 'ROOM')
  const equipment = resources.filter((r) => r.kind === 'EQUIPMENT')
  const roomName = (id: string | null) => (id ? rooms.find((room) => room.id === id)?.name : undefined)
  // Sprint 3 (1.16.0): the people filter keeps rooms with no capacity given (unknown is not "too small").
  const needed = Number(people) || 0
  const shown = view === 'ROOM'
    ? rooms.filter((room) => !needed || !room.capacity || room.capacity >= needed)
    : equipment.filter((item) => !roomFilter || item.room_id === roomFilter)
  const anyCapacity = rooms.some((room) => room.capacity)

  // One entry per induction requirement that active resources need.
  const banners = useMemo(
    () =>
      reqs
        .map((req) => {
          const rs = resources.filter((r) => r.required_qualification_id === req.id)
          const latest = quals
            .filter((x) => x.requirement_id === req.id)
            .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))[0]
          const missing = req.prerequisite_ids.find((id) => latestStatus(id, quals) !== 'VERIFIED')
          const lockedBy = missing ? reqs.find((item) => item.id === missing)?.name ?? 'the prerequisite induction' : null
          return { req, state: latest ? latest.effective_status : 'NOT_SUBMITTED', used: rs.length > 0, lockedBy }
        })
        .filter((b) => b.used),
    [reqs, resources, quals],
  )
  const verifiedCount = banners.filter((item) => item.state === 'VERIFIED' && !item.lockedBy).length

  return (
    <>
      <h1>Book a resource</h1>{/* Sprint 3 (internal-tool UI, AI-2): no introduction line */}

      {/* Sprint 3 (compact page top): one line for all inductions instead of a large banner each.
          Sprint 3 (workspace UI): folded under "Training requirements"; review R2: open while any is not verified,
          so what blocks a booking is never hidden. */}
      {banners.length > 0 && (
        <details className="bk-access-summary" open={verifiedCount < banners.length}>
          <summary>
            Training requirements <span className={verifiedCount < banners.length ? 'is-warn' : 'is-ok'}>{verifiedCount}/{banners.length} verified</span>
          </summary>
          <div className={`bk-induction-strip ${verifiedCount === banners.length ? 'is-ok' : 'is-warn'}`}
            role="group" aria-label="Your inductions">
          <span className="bk-muted">Inductions:</span>
          {banners.map(({ req, state, lockedBy }) => {
            const ok = state === 'VERIFIED' && !lockedBy
            // Evidence for an advanced induction is accepted only after its prerequisite is verified.
            const locked = lockedBy !== null && state !== 'VERIFIED' && state !== 'PENDING'
            const text = ok ? 'verified' : locked ? `needs ${lockedBy} first` : state === 'PENDING' ? 'under review'
              : state === 'VERIFIED' ? `also needs ${lockedBy}` : state === 'NOT_SUBMITTED' ? 'not submitted' : state === 'REJECTED' ? 'rejected' : 'expired'
            return (
              <span key={req.id} className={`bk-induction-item ${ok ? 'is-ok' : 'is-warn'}`} title={req.description || undefined}>
                {ok ? <CheckIcon size={14} /> : <AlertIcon size={14} />}
                <b>{req.name}</b> <span>{text}</span>
                {!ok && !locked && state !== 'PENDING' && state !== 'VERIFIED' && (
                  <Link to={`/induction?requirement=${req.id}`}><UploadIcon size={14} /> Upload</Link>
                )}
              </span>
            )
          })}
          </div>
        </details>
      )}

      <div className="bk-pills bk-mode" role="tablist" aria-label="How to book">
        {([['browse', 'Browse resources'], ['find', 'Find a free time']] as const).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={mode === key} className={`bk-pill ${mode === key ? 'is-on' : ''}`} onClick={() => setMode(key)}>
            {label}
          </button>
        ))}
      </div>

      {mode === 'find' && <FindTime resources={resources} onPick={(resource, start, minutes, date) => setPicked({ resource, start, minutes, date })} />}

      {mode === 'browse' && <>
      {/* Sprint 3 (fluency V2): only tabs scroll; resource filters have their own row. */}
      <div className="bk-browse-toolbar">
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
      </div>
      </div>
      {(view === 'ROOM' && anyCapacity || view === 'EQUIPMENT') && <div className="bk-resource-filters">
        {view === 'ROOM' && anyCapacity && (
          <label className="bk-people-filter">Fits at least{/* Sprint 3 (1.16.0) */}
            <input type="number" min={1} max={1000} inputMode="numeric" aria-label="Fits at least this many people" value={people}
              placeholder="any" onChange={(e) => setPeople(e.target.value)} /> people
          </label>
        )}
        {view === 'EQUIPMENT' && (
          <select className="bk-room-filter" aria-label="Filter equipment by room" value={roomFilter} onChange={(e) => setRoomFilter(e.target.value)}>
            <option value="">All rooms</option>
            {rooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
          </select>
        )}
      </div>}

      <h2 className="bk-h2">
        {view === 'ROOM' ? 'Rooms' : roomFilter ? `Equipment in ${roomName(roomFilter)}` : 'Equipment'}
        <small>{shown.length} {view === 'ROOM' ? (shown.length === 1 ? 'room' : 'rooms') : (shown.length === 1 ? 'device' : 'devices')}</small>
      </h2>
      {/* Sprint 3 (1.16.0): rooms and equipment are booked separately (agreed with Loy, 25 Oct). */}
      <p className="bk-muted bk-separate">{SEPARATE_BOOKING_TEXT[view]}</p>
      {error && <p className="bk-error">{error}</p>}
      <div className="bk-grid">
        {shown.map((r) => (
          <ResourceCard
            key={r.id}
            testOverride={Boolean(user?.bypass_booking_rules)}
            resource={r}
            state={stateFor(r, quals, reqs)}
            prerequisiteName={prerequisiteName(r, quals, reqs)}
            onOpen={() => setOpen(r)}
            onAdditionalHours={() => setAdditional(r)}
            onLongBooking={() => setLongBooking(r)}
            roomName={r.kind === 'EQUIPMENT' ? roomName(r.room_id) : undefined}
            equipmentCount={r.kind === 'ROOM' ? equipment.filter((item) => item.room_id === r.id).length : undefined}
            onShowEquipment={r.kind === 'ROOM' ? () => { setView('EQUIPMENT'); setRoomFilter(r.id) } : undefined}
            onRepeat={isStaff ? () => setRepeat(r) : undefined}
          />
        ))}
      </div>
      {shown.length === 0 && !error && <p className="bk-muted">{term ? 'Nothing matches your search.' : 'Nothing to show here yet.'}</p>}
      </>}

      {open && (
        <Modal label={`Book ${open.name}`} onClose={() => setOpen(null)}>
          <BookingForm resource={open} onBooked={onBooked} />
        </Modal>
      )}
      {repeat && (
        <Modal label={`Repeat weekly: ${repeat.name}`} onClose={() => setRepeat(null)}>
          <RecurringBookingForm resource={repeat} onBooked={() => { setRepeat(null); onBooked() }} />
        </Modal>
      )}
      {additional && <Modal label={`Request additional hours: ${additional.name}`} onClose={() => setAdditional(null)}>
        <AdditionalHoursForm resource={additional} onBooked={() => { setAdditional(null); onBooked() }} />
      </Modal>}
      {longBooking && <Modal label={`Request a longer booking: ${longBooking.name}`} onClose={() => setLongBooking(null)}>
        <LongBookingForm resource={longBooking} onBooked={() => { setLongBooking(null); onBooked() }} />
      </Modal>}
      {picked && (
        <Modal label={`Book ${picked.resource.name}`} onClose={() => setPicked(null)}>
          <BookingForm resource={picked.resource} onBooked={onBooked} initialDate={picked.date}
            initialStart={picked.start} initialMinutes={picked.minutes} />
        </Modal>
      )}
    </>
  )
}
