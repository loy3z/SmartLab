// Sprint 3: notification helpers (badge, link, tone).
import type { AppNotification } from '../../api/types/index.ts'

/** Text for the bell badge: nothing at 0, "99+" above 99. */
export function badgeText(unread: number): string {
  if (unread <= 0) return ''
  return unread > 99 ? '99+' : String(unread)
}

/** App route to open for a notification (only internal paths; anything else falls back to My Bookings). */
export function notificationTarget(item: Pick<AppNotification, 'link'>): string {
  const link = item.link ?? ''
  return /^\/[a-z0-9/-]*(\?[\w=&%-]*)?$/i.test(link) && !link.startsWith('//') ? link : '/bookings'
}

/** Short tone for a notification kind, used for the dot colour. */
export function notificationTone(kind: string): 'good' | 'bad' | 'info' {
  if (/APPROVED|VERIFIED|PROMOTED|UNFROZEN|CREATED_FOR_YOU/.test(kind) && !/UNFREEZE_REJECTED/.test(kind)) return 'good'
  if (/REJECTED|CANCELLED|FROZEN|NO_SHOW|EXPIRED/.test(kind) && kind !== 'INDUCTION_EXPIRING') return 'bad'
  return 'info'
}

// Sprint 3 (1.15.0): icon, Today/Earlier groups and when the bell should ring.

export type NotificationIcon = 'check' | 'cross' | 'clock' | 'info'

/**
 * Icon shown before a notification.
 * Reminders (BOOKING_REMINDER, INDUCTION_EXPIRING, anything with REMINDER) get a clock;
 * otherwise the tone decides: good → check, bad → cross, info → info.
 */
export function notificationIcon(kind: string): NotificationIcon {
  if (/REMINDER|EXPIRING/.test(kind)) return 'clock'
  const tone = notificationTone(kind)
  return tone === 'good' ? 'check' : tone === 'bad' ? 'cross' : 'info'
}

/** Calendar day (YYYY-MM-DD) in Sydney, the time zone every booking uses. */
function sydneyDay(time: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Australia/Sydney' }).format(new Date(time))
}

export interface NotificationGroup<T> { label: 'Today' | 'Earlier'; items: T[] }

/**
 * Splits notifications into "Today" (same Sydney day as `now`) and "Earlier", keeping their order.
 * Empty groups are left out, so an empty list gives [].
 */
export function groupNotifications<T extends Pick<AppNotification, 'created_at'>>(items: T[], now: number): NotificationGroup<T>[] {
  const today = sydneyDay(now)
  const groups: NotificationGroup<T>[] = [{ label: 'Today', items: [] }, { label: 'Earlier', items: [] }]
  for (const item of items) groups[sydneyDay(Date.parse(item.created_at)) === today ? 0 : 1].items.push(item)
  return groups.filter((group) => group.items.length > 0)
}

/**
 * Whether the bell should swing after a refresh: only when the unread count went up.
 * The first load of the page never rings (`previous` is null then), so opening the site is quiet.
 */
export function shouldRing(previous: number | null, next: number): boolean {
  return previous !== null && next > previous
}
