// Sprint 3 (1.19.0): shared active announcements on student and staff home pages.
import { useEffect, useState } from 'react'
import { listAnnouncements } from '../../api/index.ts'
import { errorMessage, fmtDate, fmtDateTime } from '../booking/format'
import type { Announcement } from '../../api/types/index.ts'
import { dateTimeInput } from './dates'

export function AnnouncementText({ item }: { item: Announcement }) {
  return <>
    <h3>{item.title}</h3>
    <p className="announcement-body">{item.body}</p>
    {item.expected_back && <p>Expected back: {fmtDateTime(item.expected_back)} (Sydney time)</p>}
    <p className="announcement-author">Posted by {item.author.display_name} ({item.author.role === 'MANAGER' ? 'Manager' : 'Admin'}) · {fmtDate(dateTimeInput(item.kind === 'RESOURCE_STATUS' ? item.updated_at ?? item.created_at : item.created_at).slice(0, 10))}</p>
  </>
}

export function AnnouncementBoard() {
  const [items, setItems] = useState<Announcement[]>([])
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    listAnnouncements().then(data => { if (active) { setItems(data.results); setError('') } })
      .catch(reason => { if (active) setError(errorMessage(reason)) })
    return () => { active = false }
  }, [retry])
  if (error) return <div className="announcement-error" role="alert">Announcements could not be loaded: {error} <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setRetry(value => value + 1)}>Retry announcements</button></div>
  if (!items.length) return null
  return <section className="announcement-board" aria-label="Announcements">
    <h2>Announcements</h2>
    {items.map(item => <article key={item.id}><AnnouncementText item={item} /></article>)}
  </section>
}
