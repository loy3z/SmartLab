// Sprint 3 (1.19.0): shared active announcements on student and staff home pages.
import { fmtDate, fmtDateTime } from '../booking/format'
import type { Announcement } from '../../api/types/index.ts'
import { dateTimeInput } from './dates'
import type { useAnnouncements } from './use-announcements'

export function AnnouncementText({ item }: { item: Announcement }) {
  return <>
    <h3>{item.title}</h3>
    <p className="announcement-body">{item.body}</p>
    {item.expected_back && <p>Expected back: {fmtDateTime(item.expected_back)} (Sydney time)</p>}
    <p className="announcement-author">Posted by {item.author.display_name} ({item.author.role === 'MANAGER' ? 'Manager' : 'Admin'}) · {fmtDate(dateTimeInput(item.kind === 'RESOURCE_STATUS' ? item.updated_at ?? item.created_at : item.created_at).slice(0, 10))}</p>
  </>
}

// Sprint 3 (fluency V5): the home owns loading, so the board cannot insert itself after home content.
export function AnnouncementBoard({ announcements }: { announcements: ReturnType<typeof useAnnouncements> }) {
  const { items, error, retry } = announcements
  if (error) return <div className="announcement-error" role="alert">Announcements could not be loaded: {error} <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={retry}>Retry announcements</button></div>
  if (!items.length) return null
  return <section className="announcement-board" aria-label="Announcements">
    <h2>Announcements</h2>
    {items.map(item => <article key={item.id}><AnnouncementText item={item} /></article>)}
  </section>
}
