// Sprint 3 (1.19.0): staff manual announcements with server-enforced ownership.
import { useEffect, useId, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/auth-context'
import { createAnnouncement, listAnnouncements, removeAnnouncement, updateAnnouncement } from '../booking/api'
import { errorMessage } from '../booking/format'
import { Modal } from '../booking/Modal'
import type { Announcement } from '../booking/types'
import { AnnouncementText } from './AnnouncementBoard'
import { dateTimeInput, dateTimeISO } from './dates'

export function AnnouncementsPage() {
  const fieldId = useId()
  const { user } = useAuth()
  const [items, setItems] = useState<Announcement[]>([])
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [expires, setExpires] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [removing, setRemoving] = useState<Announcement | null>(null)
  const [error, setError] = useState('')
  const [removeError, setRemoveError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    listAnnouncements(true).then(data => { if (active) setItems(data.results) })
      .catch(reason => { if (active) setError(errorMessage(reason)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [revision])
  function reset() { setEditing(null); setTitle(''); setBody(''); setExpires('') }
  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      const values = { title: title.trim(), body: body.trim(), expires_at: dateTimeISO(expires) }
      if (editing) await updateAnnouncement(editing, values)
      else await createAnnouncement(values)
      reset(); setRevision(value => value + 1)
    } catch (reason) { setError(errorMessage(reason)) }
    finally { setBusy(false) }
  }
  async function remove() {
    if (!removing || busy) return
    setBusy(true); setRemoveError('')
    try {
      await removeAnnouncement(removing.id)
      setRemoving(null); setRevision(value => value + 1)
    } catch (reason) { setRemoveError(errorMessage(reason)) }
    finally { setBusy(false) }
  }
  return <div className="announcements-page">
    <h1>Announcements</h1>
    <section className="app-card announcement-editor">
      <h2>{editing ? 'Edit announcement' : 'New announcement'}</h2>
      <form onSubmit={event => void save(event)}>
        <div className="ui-field"><label htmlFor={`${fieldId}-title`}>Title</label><input id={`${fieldId}-title`} required maxLength={120} value={title} onChange={event => setTitle(event.target.value)} /></div>
        <div className="ui-field"><label htmlFor={`${fieldId}-body`}>Message</label><textarea id={`${fieldId}-body`} required rows={4} maxLength={1000} value={body} onChange={event => setBody(event.target.value)} /></div>
        <div className="ui-field"><label htmlFor={`${fieldId}-expires`}>Remove at (optional)</label><input id={`${fieldId}-expires`} type="datetime-local" value={expires} onChange={event => setExpires(event.target.value)} /></div>
        <p className="announcement-time-note">Dates and times use Australia/Sydney. Leave blank to keep the announcement until it is removed.</p>
        {error && <p className="bk-error" role="alert">{error}</p>}
        <div className="announcement-actions"><button className="ui-btn ui-btn-primary" disabled={busy || !title.trim() || !body.trim()}>{busy ? 'Saving…' : editing ? 'Save changes' : 'Publish announcement'}</button>
          {editing && <button type="button" className="ui-btn ui-btn-ghost" disabled={busy} onClick={reset}>Cancel edit</button>}</div>
      </form>
    </section>
    <section className="announcement-history" aria-label="Published announcements">
      <h2>Published announcements</h2>
      {loading && <p role="status">Loading announcements…</p>}
      {!loading && !items.length && <p>No announcements have been published.</p>}
      {items.map(item => <article key={item.id}>
        <span className="ui-pill">{item.removed_at ? 'Removed' : item.active ? 'Active' : 'Expired'}</span>
        {item.kind === 'RESOURCE_STATUS' && <span className="ui-pill">From room status</span>}
        <AnnouncementText item={item} />
        {item.kind === 'MANUAL' && !item.removed_at && <div className="announcement-actions">
          {item.created_by === user?.id && <button className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy} aria-label={`Edit ${item.title}`} onClick={() => {
            setEditing(item.id); setTitle(item.title); setBody(item.body); setExpires(dateTimeInput(item.expires_at)); setError('')
          }}>Edit</button>}
          {(item.created_by === user?.id || user?.role === 'MANAGER') && <button className="ui-btn ui-btn-reject ui-btn-sm" disabled={busy} aria-label={`Remove ${item.title}`} onClick={() => { setRemoveError(''); setRemoving(item) }}>Remove</button>}
        </div>}
      </article>)}
    </section>
    {removing && <Modal label="Remove announcement" onClose={() => { if (!busy) setRemoving(null) }}>
      <h2>Remove announcement</h2><p>Remove “{removing.title}” from the home pages?</p>
      {removeError && <p className="bk-error" role="alert">{removeError}</p>}
      <div className="announcement-actions"><button className="ui-btn ui-btn-reject" disabled={busy} onClick={() => void remove()}>{busy ? 'Removing…' : 'Remove announcement'}</button>
        <button className="ui-btn ui-btn-ghost" disabled={busy} onClick={() => setRemoving(null)}>Keep announcement</button></div>
    </Modal>}
  </div>
}
