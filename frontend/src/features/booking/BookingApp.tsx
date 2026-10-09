import { useEffect, useState } from 'react'
import { BookingForm } from './BookingForm'
import { demoLogin, getToken, listResources, setToken } from './api'
import { errorMessage } from './format'
import { MyBookings } from './MyBookings'
import type { Resource } from './types'
import './booking.css'

/** Dev-only login so this feature works before frontend A's login lands. */
function DevLogin({ onDone }: { onDone: () => void }) {
  const [zid, setZid] = useState('z1000001')
  const [error, setError] = useState('')
  return (
    <div className="bk-card">
      <p className="bk-muted">Dev login (demo mode only; replaced by the real login page).</p>
      <input value={zid} onChange={(e) => setZid(e.target.value)} />{' '}
      <button
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
  )
}

export function BookingApp() {
  const [authed, setAuthed] = useState(!!getToken())
  const [tab, setTab] = useState<'browse' | 'mine'>('browse')
  const [kind, setKind] = useState('')
  const [q, setQ] = useState('')
  const [resources, setResources] = useState<Resource[]>([])
  const [selected, setSelected] = useState<Resource | null>(null)
  const [error, setError] = useState('')
  const [bump, setBump] = useState(0)

  useEffect(() => {
    if (!authed) return
    const t = setTimeout(() => {
      listResources({ kind, q })
        .then((r) => (setResources(r.results.filter((x) => x.active)), setError('')))
        .catch((e) => setError(errorMessage(e)))
    }, 250)
    return () => clearTimeout(t)
  }, [authed, kind, q])

  if (!authed) return <DevLogin onDone={() => setAuthed(true)} />

  return (
    <div className="bk-root">
      <nav className="bk-row">
        <button className={tab === 'browse' ? 'bk-tab-on' : ''} onClick={() => setTab('browse')}>
          Book a resource
        </button>
        <button className={tab === 'mine' ? 'bk-tab-on' : ''} onClick={() => setTab('mine')}>
          My bookings
        </button>
      </nav>
      {tab === 'mine' ? (
        <MyBookings refreshKey={bump} />
      ) : (
        <>
          <div className="bk-row">
            <input placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All</option>
              <option value="ROOM">Rooms / labs</option>
              <option value="EQUIPMENT">Equipment</option>
            </select>
          </div>
          {error && <p className="bk-error">{error}</p>}
          <div className="bk-grid">
            {resources.map((r) => (
              <button
                key={r.id}
                className={`bk-card bk-res ${selected?.id === r.id ? 'bk-slot-on' : ''}`}
                onClick={() => setSelected(r)}
              >
                <b>{r.name}</b>
                <small>{r.kind === 'ROOM' ? 'Room' : 'Equipment'} · {r.location}</small>
                <small>{r.description}</small>
              </button>
            ))}
            {resources.length === 0 && !error && <p>No resources found.</p>}
          </div>
          {selected && (
            <BookingForm key={selected.id} resource={selected} onBooked={() => setBump((n) => n + 1)} />
          )}
        </>
      )}
    </div>
  )
}
