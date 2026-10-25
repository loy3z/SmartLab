import { useCallback, useEffect, useState } from 'react'
import { EmptyState, PageHeader, RefreshStamp } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { checkCalendarConnection, getCalendarSync, processCalendarSync, retryCalendarSync } from '../booking/api'
import { errorMessage, fmtRange, fmtRelative } from '../booking/format'
import type { CalendarSyncItem, CalendarSyncStatus } from '../booking/types'
import { connectionSummary, syncErrorText, syncPill } from './calendar-sync'

/**
 * Development aid (Admin/Manager): is the Outlook connection working and did each approved booking reach the
 * calendar? Sync is one-way, so this page only shows what SmartLab wrote; it never reads people's calendars.
 */
export function CalendarSyncPage() {
  const feedback = useFeedback()
  const [status, setStatus] = useState<CalendarSyncStatus | null>(null)
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let active = true
    getCalendarSync()
      .then((data) => {
        if (!active) return
        setStatus(data)
        setLoadedAt(Date.now())
        setLoadError('')
      })
      .catch((e: unknown) => active && setLoadError(errorMessage(e)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [refresh])

  const reload = useCallback(() => {
    setLoading(true)
    setRefresh((n) => n + 1)
  }, [])

  async function run(key: string, action: () => Promise<string>, failure: string) {
    if (busy) return
    setBusy(key)
    try {
      feedback.success(await action())
    } catch (e) {
      feedback.error(errorMessage(e), failure)
    } finally {
      setBusy(null)
      reload()
    }
  }

  const check = () => run('check', async () => {
    const result = await checkCalendarConnection()
    if (!result.ok) throw new Error(syncErrorText(result.code))
    return `Connected${result.owner ? ` as ${result.owner}` : ''}.`
  }, 'Outlook connection problem')
  const sync = () => run('sync', async () => {
    const result = await processCalendarSync()
    return result.processed_count ? `Processed ${result.processed_count} waiting update(s).` : 'Nothing was waiting.'
  }, 'Could not sync')
  const retry = (item: CalendarSyncItem) => run(`retry:${item.booking_id}`, async () => {
    const booking = await retryCalendarSync(item.booking_id)
    if (booking.outlook_sync?.status === 'FAILED') throw new Error(syncErrorText(booking.outlook_sync.last_error))
    return 'Calendar updated.'
  }, 'Retry failed')

  const summary = status ? connectionSummary(status) : null
  const now = loadedAt ?? 0
  const tone = summary?.tone === 'green' ? 'ok' : summary?.tone === 'red' ? 'error' : summary?.tone === 'amber' ? 'warn' : 'blue'

  return (
    <>
      <PageHeader
        title="Calendar sync"
        actions={<RefreshStamp at={loadedAt} onRefresh={reload} busy={loading && loadedAt !== null} />}
      />

      {loadError && <p className="bk-error" role="alert">{loadError}</p>}
      {loading && !status && <p role="status">Loading calendar sync…</p>}

      {status && summary && (
        <>
          <div className={`ui-callout is-${tone}`} role="status" aria-label="Outlook connection">
            <div>
              <strong>{summary.title}</strong>
              <span>{summary.detail}</span>
              {status.last_check && <span className="ui-sub-text">Last checked {fmtRelative(status.last_check.at, now)}</span>}
            </div>
          </div>
          <div className="ui-toolbar">
            <div className="ui-filters" aria-label="Calendar totals">
              <span className="ui-pill is-green">Synced {status.summary.synced}</span>
              <span className="ui-pill is-amber">Waiting {status.summary.pending}</span>
              <span className="ui-pill is-red">Failed {status.summary.failed}</span>
            </div>
            <div className="ui-page-actions">
              <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy !== null || !status.configured} onClick={() => void check()}>
                {busy === 'check' ? 'Checking…' : 'Check connection'}
              </button>
              <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy !== null || !status.enabled} onClick={() => void sync()}>
                {busy === 'sync' ? 'Syncing…' : 'Sync now'}
              </button>
            </div>
          </div>

          {status.items.length === 0 ? (
            <EmptyState title="Nothing in Outlook yet">
              {status.enabled ? 'Approved bookings appear here once they are written to Outlook.' : 'Turn calendar sync on to write approved bookings to Outlook.'}
            </EmptyState>
          ) : (
            <div className="ui-table-wrap">
              <table className="ui-table" aria-label="Calendar sync by booking">
                <thead>
                  <tr>
                    <th>Booked for</th>
                    <th>Resource</th>
                    <th>Time</th>
                    <th>Calendar</th>
                    <th><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {status.items.map((item) => {
                    const pill = syncPill(item)
                    return (
                      <tr key={item.booking_id} className={item.sync.status === 'FAILED' ? 'is-selected' : undefined}>
                        <td>
                          <span className="ui-primary-text">{item.booked_for?.display_name ?? 'Unknown person'}</span>
                          <span className="ui-sub-text">{item.booked_for?.zid}{item.invited ? ' · invited' : ''}</span>
                          {item.booked_by && <span className="ui-sub-text">Booked by {item.booked_by.display_name} ({item.booked_by.zid})</span>}
                        </td>
                        <td>{item.urgent && <span className="ui-badge-urgent">URGENT</span>} {item.resource.name ?? 'Resource'}</td>
                        <td>{fmtRange(item.start, item.end)}</td>
                        <td>
                          <span className={`ui-pill is-${pill.tone}`}>{pill.text}</span>
                          {item.sync.status === 'FAILED' && (
                            <span className="ui-sub-text">
                              {syncErrorText(item.sync.last_error)}
                              {item.sync.next_attempt_at ? ` Next try ${fmtRelative(item.sync.next_attempt_at, now)}.` : ''}
                            </span>
                          )}
                        </td>
                        <td>
                          <div className="ui-actions">
                            {item.sync.status === 'FAILED' && (
                              <button type="button" className="ui-btn ui-btn-sm" disabled={busy !== null} onClick={() => void retry(item)}>
                                {busy === `retry:${item.booking_id}` ? 'Retrying…' : 'Retry'}
                              </button>
                            )}
                            {item.sync.web_link && (
                              <a className="ui-btn ui-btn-ghost ui-btn-sm" href={item.sync.web_link} target="_blank" rel="noreferrer">Open in Outlook</a>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  )
}
