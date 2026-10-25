// Sprint 3: notification bell in the top bar.
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { listNotifications, markAllNotificationsRead, markNotificationRead } from '../booking/api'
import { errorMessage, fmtRelative } from '../booking/format'
import type { AppNotification } from '../booking/types'
import { badgeText, groupNotifications, notificationIcon, notificationTarget, shouldRing, type NotificationIcon } from './notifications'
import './notifications.css'

const REFRESH_MS = 60_000

/** Bell in the top bar: unread count and the latest notifications. Reads on open, on window focus and every minute. */
export function NotificationBell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<AppNotification[]>([])
  const [unread, setUnread] = useState(0)
  const [error, setError] = useState('')
  const [now, setNow] = useState(() => Date.now())
  const wrapper = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  // Sprint 3 (1.15.0): the bell swings when the unread count goes up. lastUnread is null until the first
  // load, so opening the site does not ring. Changing ringKey re-mounts the icon, which restarts the animation.
  const lastUnread = useRef<number | null>(null)
  const [ringKey, setRingKey] = useState(0)

  const load = useCallback(async () => {
    try {
      const data = await listNotifications({ limit: 20 })
      setItems(data.results)
      setUnread(data.unread_count)
      if (shouldRing(lastUnread.current, data.unread_count)) setRingKey((key) => key + 1)
      lastUnread.current = data.unread_count
      setNow(Date.now())
      setError('')
    } catch (e) {
      setError(errorMessage(e))
    }
  }, [])

  useEffect(() => {
    const first = window.setTimeout(() => void load(), 0)
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    const onFocus = () => void load()
    window.addEventListener('focus', onFocus)
    return () => { window.clearTimeout(first); window.clearInterval(timer); window.removeEventListener('focus', onFocus) }
  }, [load])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !wrapper.current?.contains(event.target)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); button.current?.focus() }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => { document.removeEventListener('pointerdown', onPointerDown); document.removeEventListener('keydown', onKeyDown) }
  }, [open])

  async function openItem(item: AppNotification) {
    setOpen(false)
    if (!item.read_at) {
      setItems((list) => list.map((entry) => entry.id === item.id ? { ...entry, read_at: new Date().toISOString() } : entry))
      setUnread((count) => Math.max(0, count - 1))
      if (lastUnread.current !== null) lastUnread.current = Math.max(0, lastUnread.current - 1)
      void markNotificationRead(item.id).catch(() => undefined)
    }
    navigate(notificationTarget(item))
  }

  async function readAll() {
    await markAllNotificationsRead().catch(() => undefined)
    await load()
  }

  const badge = badgeText(unread)
  return (
    <div className="nt-bell" ref={wrapper}>
      <button
        ref={button}
        type="button"
        className="app-icon-button nt-bell-button"
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
        aria-controls="nt-panel"
        onClick={() => { setOpen((value) => !value); if (!open) void load() }}
      >
        {/* Sprint 3 (1.15.0): key restarts the swing; nt-ring only after a new notification (ringKey > 0). */}
        <svg key={ringKey} className={ringKey ? 'nt-bell-icon nt-ring' : 'nt-bell-icon'} width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
          <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9" /><path d="M10 20a2 2 0 0 0 4 0" />
        </svg>
        {/* key={badge}: a new number re-mounts the badge, so it pops. */}
        {badge && <span key={badge} className="nt-badge" aria-hidden="true">{badge}</span>}
      </button>
      {open && (
        <div className="nt-panel" id="nt-panel" role="region" aria-label="Notifications">
          <div className="nt-panel-head">
            <strong>Notifications</strong>
            <button type="button" className="nt-link" disabled={unread === 0} onClick={() => void readAll()}>Mark all as read</button>
          </div>
          {error && <p className="nt-empty" role="alert">{error}</p>}
          {!error && items.length === 0 && <p className="nt-empty">No notifications yet.</p>}
          {/* Sprint 3 (1.15.0): Today / Earlier groups, an icon per kind, body cut to two lines. */}
          <div className="nt-list">
            {groupNotifications(items, now).map((group) => (
              <section key={group.label} className="nt-group" aria-label={group.label}>
                <h3 className="nt-group-title">{group.label}</h3>
                <ul>
                  {group.items.map((item) => {
                    const icon = notificationIcon(item.kind)
                    return (
                      <li key={item.id}>
                        <button type="button" className={`nt-item${item.read_at ? '' : ' is-unread'}`} onClick={() => void openItem(item)}>
                          <span className={`nt-icon is-${icon}`} aria-hidden="true"><KindIcon icon={icon} /></span>
                          <span className="nt-text">
                            <span className="nt-title-row">
                              <strong>{item.title}</strong>
                              <small>{fmtRelative(item.created_at, now)}</small>
                            </span>
                            <span className="nt-body">{item.body}</span>
                            {!item.read_at && <span className="sr-only">Unread</span>}
                          </span>
                          {!item.read_at && <i className="nt-unread-dot" aria-hidden="true" />}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </section>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Small line icons for notification kinds (see notificationIcon). */
function KindIcon({ icon }: { icon: NotificationIcon }) {
  const paths: Record<NotificationIcon, ReactNode> = {
    check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
    cross: <path d="M7 7l10 10M17 7L7 17" />,
    clock: <><circle cx="12" cy="12" r="8" /><path d="M12 8v4.5l3 2" /></>,
    info: <><circle cx="12" cy="12" r="8" /><path d="M12 11v5M12 8h.01" /></>,
  }
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{paths[icon]}</svg>
}
