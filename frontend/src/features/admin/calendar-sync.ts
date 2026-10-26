import type { CalendarCheck, CalendarSyncItem, CalendarSyncStatus } from '../../api/types/index.ts'

export type Tone = 'green' | 'amber' | 'red' | 'grey' | 'blue'

/** Plain-language meaning of a sync or connection error code, with what to do next. */
export function syncErrorText(code: string | null | undefined): string {
  if (!code) return ''
  const known: Record<string, string> = {
    TOKEN_EXPIRED: 'Microsoft sign-in expired. Sign in again on the server computer, then retry.',
    GRAPH_HTTP_401: 'Microsoft sign-in expired. Sign in again on the server computer, then retry.',
    OUTLOOK_LOGIN_EXPIRED: 'Microsoft sign-in expired. Run outlook_login again on the server computer.',
    OUTLOOK_NOT_CONFIGURED: 'Outlook is not set up on the server yet.',
    OUTLOOK_INVALID_TOKEN_FILE: 'The saved Microsoft sign-in is unreadable. Sign in again.',
    GRAPH_HTTP_403: 'The Microsoft account has no permission to change this calendar.',
    OUTLOOK_CALENDAR_READ_ONLY: 'The Microsoft account can only read this calendar.',
    GRAPH_HTTP_404: 'The calendar was not found.',
    GRAPH_HTTP_429: 'Microsoft asked us to slow down. It will retry by itself.',
    GRAPH_NETWORK_ERROR: 'Microsoft could not be reached. It will retry by itself.',
    STUDENT_EMAIL_NOT_CONFIGURED: 'The person has no university email address.',
  }
  return known[code] ?? `Error ${code}.`
}

export function syncPill(item: CalendarSyncItem): { tone: Tone; text: string } {
  const { status, action } = item.sync
  if (status === 'FAILED') return { tone: 'red', text: 'Failed' }
  if (status === 'PENDING' || status === 'IN_PROGRESS') return { tone: 'amber', text: status === 'PENDING' ? 'Waiting' : 'Syncing' }
  if (action === 'DELETE') return { tone: 'grey', text: 'Removed (cancelled)' }
  return { tone: 'green', text: action === 'UPDATE' ? 'Synced (updated)' : 'Synced' }
}

export function connectionSummary(status: CalendarSyncStatus): { tone: Tone; title: string; detail: string } {
  if (!status.enabled) return { tone: 'grey', title: 'Calendar sync is off', detail: 'Set OUTLOOK_ENABLED=true on the server to write approved bookings to Outlook.' }
  if (!status.configured) return { tone: 'red', title: 'Outlook is not set up', detail: syncErrorText('OUTLOOK_NOT_CONFIGURED') }
  const check: CalendarCheck | null = status.last_check
  if (!check) return { tone: 'amber', title: 'Connection not checked yet', detail: 'Use “Check connection” to test the Microsoft sign-in.' }
  if (!check.ok) return { tone: 'red', title: 'Outlook connection problem', detail: syncErrorText(check.code) }
  const owner = check.owner ? ` as ${check.owner}` : ''
  return { tone: 'green', title: 'Connected to Outlook', detail: `Writing to ${check.calendar_name ?? 'the calendar'}${owner}.` }
}
