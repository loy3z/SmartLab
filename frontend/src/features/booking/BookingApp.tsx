// Book a resource: browse rooms and equipment (search, people filter, room filter) or find a free time, then open the
// booking dialogs. Authentication, routing and the page layout belong to app/.
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useAuth } from '../auth/auth-context'
import { BookingForm } from './BookingForm'
import { AdditionalHoursForm } from './AdditionalHoursForm'
import { LongBookingForm } from './LongBookingForm'
import { FindTime } from './FindTime'
import { listQualifications, listRequirements, listResources } from '../../api/index.ts'
import { errorMessage, SEPARATE_BOOKING_TEXT } from './format'
import { SearchIcon } from './icons'
import { Modal } from './Modal'
import { RecurringBookingForm } from './RecurringBookingForm'
import { ResourceCard, type InductionState } from './ResourceCard'
import type { Qualification, Requirement, Resource } from '../../api/types/index.ts'

/** The newest evidence decides the status, not any older approval (the same rule as the server). */
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

/** The first prerequisite induction that is not verified yet, for the "needed first" chip. */
function missingPrerequisite(r: Resource, quals: Qualification[], reqs: Requirement[]): Requirement | undefined {
  const requirement = reqs.find((item) => item.id === r.required_qualification_id)
  const missing = requirement?.prerequisite_ids.find((id) => latestStatus(id, quals) !== 'VERIFIED')
  return missing ? reqs.find((item) => item.id === missing) : undefined
}

/** Where the card's induction chip leads when the student still has evidence to submit. */
function inductionLink(r: Resource, state: InductionState, prerequisite: Requirement | undefined): string | undefined {
  if (state === 'PREREQUISITE_REQUIRED') return prerequisite && `/induction?requirement=${prerequisite.id}`
  if (state === 'NOT_SUBMITTED' || state === 'REJECTED' || state === 'EXPIRED') return `/induction?requirement=${r.required_qualification_id}`
  return undefined
}

/** Rooms and devices are booked separately (a room booking does not include the devices in it). */
type View = 'ROOM' | 'EQUIPMENT'
/** "Find a free time" starts from a day and length; "browse" starts from a resource. */
type Mode = 'browse' | 'find'
/** A time chosen in Find a free time, handed to the booking dialog as its starting selection. */
interface Picked { resource: Resource; start: string; minutes: number; date: string }

/** Frontend B's resource page; authentication, routing and layout are owned by app/. */
export function BookingApp({ onBooked }: { onBooked: () => void }) {
  const { user } = useAuth()
  const isStaff = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const isManager = user?.role === 'MANAGER'
  // Opened from "Request additional hours" on the Dashboard: each card's main button opens that form.
  const [params, setParams] = useSearchParams()
  const forAdditionalHours = params.get('for') === 'additional-hours'
  const [repeat, setRepeat] = useState<Resource | null>(null) // Weekly series dialog
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
  const [people, setPeople] = useState('') // Rooms that fit at least this many people

  // Reload induction evidence when a dialog closes: the person may have just come back from the induction page.
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

  // The server returns one list; rooms and devices are split here. Devices know their room through room_id.
  const rooms = resources.filter((r) => r.kind === 'ROOM')
  const equipment = resources.filter((r) => r.kind === 'EQUIPMENT')
  const roomName = (id: string | null) => (id ? rooms.find((room) => room.id === id)?.name : undefined)
  // The people filter keeps rooms with no capacity given (unknown is not "too small").
  const needed = Number(people) || 0
  const shown = view === 'ROOM'
    ? rooms.filter((room) => !needed || !room.capacity || room.capacity >= needed)
    : equipment.filter((item) => !roomFilter || item.room_id === roomFilter)
  const anyCapacity = rooms.some((room) => room.capacity)

  return (
    <>
      {/* No introduction line and no induction list here; each card's induction chip links to the induction page. */}
      <h1>Book a resource</h1>

      <div className="bk-pills bk-mode" role="tablist" aria-label="How to book">
        {([['browse', 'Browse resources'], ['find', 'Find a free time']] as const).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={mode === key} className={`bk-pill ${mode === key ? 'is-on' : ''}`} onClick={() => setMode(key)}>
            {label}
          </button>
        ))}
      </div>

      {mode === 'find' && <FindTime resources={resources} onPick={(resource, start, minutes, date) => setPicked({ resource, start, minutes, date })} />}

      {mode === 'browse' && <>
      {/* Only tabs scroll; resource filters have their own row. */}
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
          <label className="bk-people-filter">Fits at least
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
      {/* Rooms and equipment are booked separately. */}
      <p className="bk-muted bk-separate">{SEPARATE_BOOKING_TEXT[view]}</p>
      {error && <p className="bk-error">{error}</p>}
      {forAdditionalHours && (
        <div className="ui-callout" role="status">
          Choose a room or equipment to request additional hours.{' '}
          <button type="button" className="bk-linkbtn" onClick={() => setParams({})}>Book normally instead</button>
        </div>
      )}
      <div className="bk-grid">
        {shown.map((r) => {
          const state = stateFor(r, quals, reqs)
          const prerequisite = missingPrerequisite(r, quals, reqs)
          return <ResourceCard
            key={r.id}
            testOverride={Boolean(user?.bypass_booking_rules)}
            managerOverride={isManager}
            resource={r}
            state={state}
            prerequisiteName={prerequisite?.name}
            inductionHref={inductionLink(r, state, prerequisite)}
            onOpen={() => (forAdditionalHours ? setAdditional(r) : setOpen(r))}
            openLabel={forAdditionalHours ? 'Request additional hours' : undefined}
            onAdditionalHours={forAdditionalHours ? undefined : () => setAdditional(r)}
            onLongBooking={() => setLongBooking(r)}
            roomName={r.kind === 'EQUIPMENT' ? roomName(r.room_id) : undefined}
            equipmentCount={r.kind === 'ROOM' ? equipment.filter((item) => item.room_id === r.id).length : undefined}
            onShowEquipment={r.kind === 'ROOM' ? () => { setView('EQUIPMENT'); setRoomFilter(r.id) } : undefined}
            onRepeat={isStaff ? () => setRepeat(r) : undefined}
          />
        })}
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
