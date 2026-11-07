// Sprint 3: Manager page to add, edit, archive and restore rooms and equipment.
// The rules live in the backend (booking/services/resources.py); resource-form.ts gives quicker messages.
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { EmptyState, PageHeader, RefreshStamp, Tabs } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { archiveResource, createResource, getResourceInternalInfo, listAllResources, listRequirements, restoreResource, updateResource,
  updateResourceInternalInfo } from '../../api/index.ts'
import { errorMessage, fmtDuration, fmtHours, fmtRange } from '../booking/format'
import type { BookingOutsideRules, Requirement, Resource, ResourceDetail, ResourceInput, ResourceInternalInput, ResourceKind } from '../../api/types/index.ts' // Sprint 3 (1.16.0): ResourceDetail
import { changedFields, checkResource, describeHours, emptyResource, hoursFromMinutes, MAX_DETAILS, minutesFromHours, PROBLEM_TEXT, resourceToInput, SLOT_CHOICES } from './resource-form' // Sprint 3 (1.16.0): hours helpers, MAX_DETAILS

type View = 'ROOM' | 'EQUIPMENT' | 'ARCHIVED'

const EMPTY_INTERNAL: ResourceInternalInput = { owner: '', asset_number: '', provided_by: '', specifications: '' }

const STATUS_TEXT: Record<Resource['status'], string> = { AVAILABLE: 'Available', MAINTENANCE: 'Maintenance', CLOSED: 'Closed' }
const STATUS_TONE: Record<Resource['status'], string> = { AVAILABLE: 'is-green', MAINTENANCE: 'is-amber', CLOSED: 'is-red' }

/** What the edit dialog is doing: adding a new resource of a kind, or editing an existing one. */
type Editing = { mode: 'add'; kind: ResourceKind } | { mode: 'edit'; resource: Resource }

export function ManagerResourcesPage() {
  const feedback = useFeedback()
  const [resources, setResources] = useState<Resource[]>([])
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [view, setView] = useState<View>('ROOM')
  const [loading, setLoading] = useState(true)
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [editing, setEditing] = useState<Editing | null>(null)
  const [outside, setOutside] = useState<{ resource: Resource; bookings: BookingOutsideRules[] } | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([listAllResources(), listRequirements()])
      .then(([resourceData, requirementData]) => {
        if (!active) return
        setResources(resourceData.results)
        setRequirements(requirementData.results)
        setLoadedAt(Date.now())
        setError('')
      })
      .catch((e: unknown) => active && setError(errorMessage(e)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [refresh])

  const reload = useCallback(() => { setLoading(true); setRefresh((n) => n + 1) }, [])

  const byId = useMemo(() => new Map(resources.map((item) => [item.id, item])), [resources])
  const requirementName = (id: string | null) => requirements.find((item) => item.id === id)?.name ?? '—'
  const listedRooms = resources.filter((item) => item.kind === 'ROOM' && item.active)
  const rows = resources.filter((item) => (view === 'ARCHIVED' ? !item.active : item.active && item.kind === view))
  const counts = {
    ROOM: resources.filter((item) => item.active && item.kind === 'ROOM').length,
    EQUIPMENT: resources.filter((item) => item.active && item.kind === 'EQUIPMENT').length,
    ARCHIVED: resources.filter((item) => !item.active).length,
  }

  async function archive(resource: Resource) {
    const answer = await feedback.confirm({
      title: `Archive ${resource.name}?`,
      message: 'It disappears from the booking pages but keeps its history. You can restore it later. A resource with future bookings, or a room that still holds equipment, cannot be archived.',
      confirmLabel: 'Archive',
      danger: true,
    })
    if (!answer.confirmed) return
    setBusyId(resource.id)
    try {
      await archiveResource(resource.id)
      feedback.success(`${resource.name} is archived.`, 'Archived')
      reload()
    } catch (e) {
      feedback.error(errorMessage(e), 'Not archived')
    } finally {
      setBusyId(null)
    }
  }

  async function restore(resource: Resource) {
    setBusyId(resource.id)
    try {
      await restoreResource(resource.id)
      feedback.success(`${resource.name} can be booked again.`, 'Restored')
      reload()
    } catch (e) {
      feedback.error(errorMessage(e), 'Not restored')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <PageHeader
        title="Resources"
        description="Changes apply to new requests only; archive a resource instead of deleting it so its history stays."
        actions={(
          <>
            <RefreshStamp at={loadedAt} onRefresh={reload} busy={loading && loadedAt !== null} />
            <button type="button" className="ui-btn ui-btn-ghost" onClick={() => setEditing({ mode: 'add', kind: 'ROOM' })}>+ Add room</button>
            <button type="button" className="ui-btn ui-btn-primary" onClick={() => setEditing({ mode: 'add', kind: 'EQUIPMENT' })}>+ Add equipment</button>
          </>
        )}
      />

      <div className="ui-toolbar">
        <Tabs
          label="Resource type"
          value={view}
          onChange={setView}
          items={[
            { key: 'ROOM', label: 'Rooms', count: loadedAt ? counts.ROOM : null },
            { key: 'EQUIPMENT', label: 'Equipment', count: loadedAt ? counts.EQUIPMENT : null },
            { key: 'ARCHIVED', label: 'Archived', count: loadedAt ? counts.ARCHIVED : null },
          ]}
        />
      </div>

      {error && <p role="alert" className="bk-error">{error}</p>}
      {loading && loadedAt === null && <p role="status">Loading resources…</p>}
      {loadedAt !== null && rows.length === 0 && (
        <EmptyState icon="–" title={view === 'ARCHIVED' ? 'Nothing archived' : 'Nothing here yet'}>
          {view === 'ARCHIVED' ? 'Archived rooms and equipment appear here.' : 'Use the buttons above to add one.'}
        </EmptyState>
      )}

      {rows.length > 0 && (
        <div className="ui-table-wrap">
          <table className="ui-table" aria-label="Resources">
            <thead>
              <tr>
                <th>Name</th>
                <th className="ui-hide-sm">{view === 'ROOM' ? 'Location' : 'Kept in'}</th>
                <th className="ui-hide-sm">Induction</th>
                <th>Hours</th>
                <th>Status</th>
                <th><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id}>
                  <td>
                    <span className="ui-primary-text">{item.name}</span>
                    {item.category && <span className="ui-sub-text">{item.category}</span>}
                  </td>
                  <td className="ui-hide-sm">{item.kind === 'EQUIPMENT' ? (byId.get(item.room_id ?? '')?.name ?? item.location) : item.location}</td>
                  <td className="ui-hide-sm">{requirementName(item.required_qualification_id)}</td>
                  <td>
                    {fmtHours(item.opening_time, item.closing_time)}{/* Sprint 3 (internal-tool UI, AI-6) */}
                    <span className="ui-sub-text">{item.slot_minutes}-min steps · up to {fmtDuration(item.max_booking_minutes)}</span>
                  </td>
                  <td>
                    {item.active
                      ? <span className={`ui-pill ${STATUS_TONE[item.status]}`}>{STATUS_TEXT[item.status]}</span>
                      : <span className="ui-pill is-grey">Archived</span>}
                  </td>
                  <td>
                    <div className="ui-actions">
                      <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" aria-label={`Edit ${item.name}`}
                        disabled={busyId !== null} onClick={() => setEditing({ mode: 'edit', resource: item })}>Edit</button>
                      {item.active ? (
                        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" aria-label={`Archive ${item.name}`}
                          disabled={busyId !== null} onClick={() => void archive(item)}>{busyId === item.id ? 'Archiving…' : 'Archive'}</button>
                      ) : (
                        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" aria-label={`Restore ${item.name}`}
                          disabled={busyId !== null} onClick={() => void restore(item)}>{busyId === item.id ? 'Restoring…' : 'Restore'}</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {outside && (
        <div className="ui-callout is-warn" role="status" aria-label="Bookings outside the new rules">
          <div>
            <strong>{outside.bookings.length} future booking(s) of {outside.resource.name} no longer fit the new rules</strong>
            <span>They are kept. Cancel or move them in Room management or Booking review if needed.</span>
            <ul>
              {outside.bookings.map((booking) => (
                <li key={booking.id}>
                  {fmtRange(booking.start, booking.end)} · {booking.student?.display_name ?? booking.student_id} ·{' '}
                  {PROBLEM_TEXT[booking.problem] ?? booking.problem}
                </li>
              ))}
            </ul>
          </div>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setOutside(null)}>Dismiss</button>
        </div>
      )}

      {editing && (
        <ResourceDialog
          editing={editing}
          rooms={listedRooms}
          requirements={requirements}
          onClose={() => setEditing(null)}
          onSaved={(resource, bookings) => {
            setEditing(null)
            setOutside(bookings.length ? { resource, bookings } : null)
            feedback.success(`${resource.name} is saved.`, editing.mode === 'add' ? 'Added' : 'Saved')
            setView(resource.kind)
            reload()
          }}
        />
      )}
    </section>
  )
}

function ResourceDialog({ editing, rooms, requirements, onClose, onSaved }: {
  editing: Editing
  rooms: Resource[]
  requirements: Requirement[]
  onClose: () => void
  onSaved: (resource: Resource, outside: BookingOutsideRules[]) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const kind: ResourceKind = editing.mode === 'add' ? editing.kind : editing.resource.kind
  const initial = useMemo(
    () => (editing.mode === 'add' ? emptyResource(requirements[0]?.id ?? '') : resourceToInput(editing.resource)),
    [editing, requirements],
  )
  const [form, setForm] = useState<ResourceInput>(initial)
  // 2026-11-07 (client, Week 8): Managers-only details, saved separately; only changed fields are sent.
  const [internalSaved, setInternalSaved] = useState<ResourceInternalInput>(EMPTY_INTERNAL)
  const [internal, setInternal] = useState<ResourceInternalInput>(EMPTY_INTERNAL)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const problems = checkResource(kind, form)
  const firstProblem = Object.values(problems)[0]

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  useEffect(() => {
    if (editing.mode !== 'edit') return
    getResourceInternalInfo(editing.resource.id).then((info) => {
      const values = { owner: info.owner, asset_number: info.asset_number, provided_by: info.provided_by, specifications: info.specifications }
      setInternalSaved(values)
      setInternal(values)
    }).catch(() => undefined) // the rest of the form still works; nothing is sent unless a field is typed in
  }, [editing])

  const set = <K extends keyof ResourceInput>(key: K, value: ResourceInput[K]) => setForm((current) => ({ ...current, [key]: value }))

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy || firstProblem) return
    setBusy(true)
    setError('')
    try {
      let saved: Resource
      let outsideRules: BookingOutsideRules[] = []
      if (editing.mode === 'add') {
        saved = await createResource(kind, form)
      } else {
        const result = await updateResource(editing.resource.id, changedFields(initial, form))
        saved = result.resource
        outsideRules = result.bookings_outside_rules
      }
      const internalChanges = Object.fromEntries(Object.entries(internal)
        .filter(([key, value]) => value !== internalSaved[key as keyof ResourceInternalInput]))
      if (Object.keys(internalChanges).length) await updateResourceInternalInfo(saved.id, internalChanges)
      onSaved(saved, outsideRules)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const title = editing.mode === 'add' ? `Add ${kind === 'ROOM' ? 'room' : 'equipment'}` : `Edit ${editing.resource.name}`
  return (
    <dialog ref={ref} className="ui-dialog" aria-labelledby="resource-dialog-title" onCancel={(e) => { e.preventDefault(); onClose() }}>
      <form className="ui-dialog-card" onSubmit={submit}>
        <h2 id="resource-dialog-title">{title}</h2>
        {editing.mode === 'edit' && (
          <p className="ui-dialog-message">The type ({kind === 'ROOM' ? 'room' : 'equipment'}) cannot change. Existing bookings are kept.</p>
        )}
        <label className="ui-field"><span>Name</span>
          <input required maxLength={120} value={form.name} onChange={(e) => set('name', e.target.value)} />
        </label>
        <label className="ui-field"><span>Location</span>
          <input required maxLength={120} value={form.location} placeholder="Building and room number" onChange={(e) => set('location', e.target.value)} />
        </label>
        {kind === 'EQUIPMENT' && (
          <>
            <label className="ui-field"><span>Kept in room</span>
              <select value={form.room_id ?? ''} onChange={(e) => set('room_id', e.target.value || null)}>
                <option value="">Not in a room</option>
                {rooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
              </select>
            </label>
            <label className="ui-field"><span>Equipment type</span>
              <input maxLength={60} value={form.category ?? ''} placeholder="e.g. Microscopy" onChange={(e) => set('category', e.target.value || null)} />
            </label>
          </>
        )}
        <label className="ui-field"><span>Induction needed to book</span>
          <select required value={form.required_qualification_id} onChange={(e) => set('required_qualification_id', e.target.value)}>
            <option value="" disabled>Choose an induction</option>
            {requirements.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <div className="mr-grid">
          <label className="ui-field"><span>Opens</span>
            <input type="time" required step={form.slot_minutes * 60} value={form.opening_time} onChange={(e) => set('opening_time', e.target.value)} />
          </label>
          <label className="ui-field"><span>Closes</span>
            <input type="time" required step={form.slot_minutes * 60} value={form.closing_time} onChange={(e) => set('closing_time', e.target.value)} />
          </label>
          <label className="ui-field"><span>Time steps</span>
            <select value={form.slot_minutes} onChange={(e) => set('slot_minutes', Number(e.target.value))}>
              {SLOT_CHOICES.map((minutes) => <option key={minutes} value={minutes}>{minutes} minutes</option>)}
            </select>
          </label>
          {/* Sprint 3 (1.16.0): hours instead of minutes (480 → 8, 1440 → 24); sent to the API as minutes. */}
          <label className="ui-field"><span>Longest booking (hours)</span>
            <input type="number" min={hoursFromMinutes(form.slot_minutes)} step={hoursFromMinutes(form.slot_minutes)}
              value={hoursFromMinutes(form.max_booking_minutes)}
              onChange={(e) => set('max_booking_minutes', minutesFromHours(Number(e.target.value)))} />
          </label>
          <label className="ui-field"><span>Review window (hours)</span>
            <input type="number" min={0.5} max={336} step={0.5} value={hoursFromMinutes(form.pending_hold_minutes)}
              onChange={(e) => set('pending_hold_minutes', minutesFromHours(Number(e.target.value)))} />
            <small className="bk-muted">If no admin decides, the system decides {describeHours(form.pending_hold_minutes)} after a request is sent.</small>
          </label>
        </div>
        <label className="ui-field"><span>Description (optional)</span>
          <textarea maxLength={1000} rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} />
        </label>
        {/* Sprint 3 (1.16.0): what people need to choose the right resource. */}
        {kind === 'ROOM' && (
          <label className="ui-field"><span>Capacity (people, optional)</span>
            <input type="number" min={1} max={1000} step={1} value={form.capacity ?? ''}
              onChange={(e) => set('capacity', e.target.value === '' ? null : Number(e.target.value))} />
          </label>
        )}
        <DetailsEditor details={form.details} onChange={(details) => set('details', details)}
          placeholder={kind === 'ROOM' ? 'e.g. Floor · Level 3' : 'e.g. Model · Rigol DS1054Z'} />
        <fieldset className="mr-details">
          <legend>Managers only</legend>
          <small className="bk-muted">Not shown to students or Admins.</small>
          <label className="ui-field"><span>Owner</span>
            <input maxLength={120} value={internal.owner} onChange={(e) => setInternal({ ...internal, owner: e.target.value })} />
          </label>
          <label className="ui-field"><span>UNSW asset number</span>
            <input maxLength={60} value={internal.asset_number} onChange={(e) => setInternal({ ...internal, asset_number: e.target.value })} />
          </label>
          <label className="ui-field"><span>Provided by</span>
            <input maxLength={120} value={internal.provided_by} placeholder="e.g. School grant 2024"
              onChange={(e) => setInternal({ ...internal, provided_by: e.target.value })} />
          </label>
          <label className="ui-field"><span>Specifications</span>
            <textarea maxLength={2000} rows={2} value={internal.specifications} onChange={(e) => setInternal({ ...internal, specifications: e.target.value })} />
          </label>
        </fieldset>
        {firstProblem && <p className="bk-muted" role="status">{firstProblem}</p>}
        {error && <p className="bk-error" role="alert">{error}</p>}
        <div className="ui-dialog-actions">
          <button type="button" className="ui-btn ui-btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="ui-btn ui-btn-primary" disabled={busy || Boolean(firstProblem)}>
            {busy ? 'Saving…' : editing.mode === 'add' ? 'Add' : 'Save changes'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

/**
 * Sprint 3 (1.16.0): "label: value" lines on a resource (e.g. Model: Rigol DS1054Z, Floor: Level 3). The lab decides
 * what to show; empty rows are ignored when saving.
 */
function DetailsEditor({ details, onChange, placeholder }: {
  details: ResourceDetail[]
  onChange: (details: ResourceDetail[]) => void
  placeholder: string
}) {
  const update = (index: number, field: keyof ResourceDetail, value: string) =>
    onChange(details.map((item, i) => (i === index ? { ...item, [field]: value } : item)))
  return (
    <fieldset className="mr-details">
      <legend>Details shown to people (optional)</legend>
      <small className="bk-muted">{placeholder}. Up to {MAX_DETAILS} lines.</small>
      {details.map((item, index) => (
        <div key={index} className="mr-detail-row">
          <input aria-label={`Detail ${index + 1} label`} maxLength={40} placeholder="Label" value={item.label} onChange={(e) => update(index, 'label', e.target.value)} />
          <input aria-label={`Detail ${index + 1} value`} maxLength={200} placeholder="Value" value={item.value} onChange={(e) => update(index, 'value', e.target.value)} />
          <button type="button" className="ui-icon-btn" aria-label={`Remove detail ${index + 1}`} onClick={() => onChange(details.filter((_, i) => i !== index))}>×</button>
        </div>
      ))}
      {details.length < MAX_DETAILS && (
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => onChange([...details, { label: '', value: '' }])}>+ Add a detail</button>
      )}
    </fieldset>
  )
}
