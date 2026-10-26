// Sprint 3: Booking Records (Admin and Manager). Who booked what and when, with filters and a CSV of the same
// list; the Usage statistics tab is the former Usage Report page.
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { EmptyState, PageHeader, Tabs } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { downloadBookingRecords, listBookingRecords, listResources } from '../../api/index.ts'
import { errorMessage, fmtDuration, fmtRange, minutesBetween, STATUS_TEXT, todaySydney } from '../booking/format'
import type { Booking, Resource } from '../../api/types/index.ts'
import { attendanceText, creatorText, defaultRecordFilters, RECORD_STATUSES, recordQuery, type RecordFilters } from './records'
import { UsageTab } from './UsageTab'

type Tab = 'records' | 'usage'

function saveCsv(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  try {
    link.click()
  } finally {
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}

function RecordsTab() {
  const feedback = useFeedback()
  const initial = useMemo(() => defaultRecordFilters(todaySydney()), [])
  const [filters, setFilters] = useState<RecordFilters>(initial)
  const [search, setSearch] = useState('') // typed text; applied on Search / Enter
  const [resources, setResources] = useState<Resource[]>([])
  const [rows, setRows] = useState<Booking[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listResources({}).then((data) => setResources(data.results)).catch(() => setResources([]))
  }, [])

  useEffect(() => {
    let active = true
    listBookingRecords(recordQuery(filters))
      .then((data) => { if (active) { setRows(data.results); setError('') } })
      .catch((e: unknown) => active && (setRows(null), setError(errorMessage(e))))
    return () => { active = false }
  }, [filters])

  const set = (changes: Partial<RecordFilters>) => setFilters((current) => ({ ...current, ...changes }))
  const resourceName = (b: Booking) => b.resource_name ?? resources.find((item) => item.id === b.resource_id)?.name ?? 'Resource'

  async function exportCsv() {
    setBusy(true)
    try {
      saveCsv(await downloadBookingRecords(recordQuery(filters)), `smartlab-bookings-${filters.from}-to-${filters.to}.csv`)
      feedback.success('The CSV has the same bookings as the table.', 'Download ready')
    } catch (e) {
      feedback.error(errorMessage(e), 'Download failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="Booking records">
      <div className="ui-toolbar">
        <form className="ui-filters" onSubmit={(e) => { e.preventDefault(); set({ q: search }) }}>
          <label>From <input type="date" aria-label="From" value={filters.from} max={filters.to} onChange={(e) => e.target.value && set({ from: e.target.value })} /></label>
          <label>To <input type="date" aria-label="To" value={filters.to} min={filters.from} onChange={(e) => e.target.value && set({ to: e.target.value })} /></label>
          <select aria-label="Resource" value={filters.resourceId} onChange={(e) => set({ resourceId: e.target.value })}>
            <option value="">All rooms and equipment</option>
            {resources.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <select aria-label="Status" value={filters.status} onChange={(e) => set({ status: e.target.value })}>
            {RECORD_STATUSES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <input type="search" aria-label="Name or zID" placeholder="Name or zID" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button type="submit" className="ui-btn ui-btn-ghost">Search</button>
        </form>
        <div className="ui-actions">
          <button type="button" className="ui-btn ui-btn-ghost" onClick={() => window.print()}>Print</button>
          <button type="button" className="ui-btn ui-btn-primary" disabled={busy || !rows?.length} onClick={() => void exportCsv()}>
            {busy ? 'Preparing…' : 'Export CSV'}
          </button>
        </div>
      </div>
      {error && <p role="alert" className="bk-error">{error}</p>}
      {!rows && !error && <p role="status">Loading bookings…</p>}
      {rows && rows.length === 0 && <EmptyState icon="–" title="No bookings match these filters" />}
      {rows && rows.length > 0 && (
        <>
          <p className="bk-muted" role="status">{rows.length} booking{rows.length === 1 ? '' : 's'}</p>
          <div className="ui-table-wrap">
            <table className="ui-table" aria-label="Bookings">
              <thead>
                <tr>
                  <th>Time</th><th>Resource</th><th>Booked for</th><th className="ui-hide-sm">Created by</th><th>Status</th><th>Attendance</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={b.id}>
                    <td className="rec-time">{fmtRange(b.start, b.end)}<span className="ui-sub-text">{fmtDuration(minutesBetween(b.start, b.end))}</span></td>
                    <td>{resourceName(b)}{b.series_id && <span className="ui-sub-text">Weekly series</span>}</td>
                    <td>
                      <span className="ui-primary-text">{b.student?.display_name ?? b.booked_for?.display_name ?? '—'}</span>
                      <span className="ui-sub-text">{b.student?.zid ?? b.booked_for?.zid}</span>
                    </td>
                    <td className="ui-hide-sm">{creatorText(b)}</td>
                    <td>
                      {STATUS_TEXT[b.status]}
                      {b.urgent && <span className="ui-badge-urgent">URGENT</span>}
                      {b.decision_reason && <span className="ui-sub-text">{b.decision_reason}</span>}
                    </td>
                    <td>{attendanceText(b)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}

export function BookingRecordsPage() {
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'usage' ? 'usage' : 'records'
  return (
    <div>
      <PageHeader
        title="Booking records"
      />
      <div className="ui-toolbar">
        <Tabs<Tab> label="Booking records view" value={tab} onChange={(key) => setParams(key === 'usage' ? { tab: 'usage' } : {})}
          items={[{ key: 'records', label: 'Records' }, { key: 'usage', label: 'Usage statistics' }]} />
      </div>
      {tab === 'records' ? <RecordsTab /> : <UsageTab />}
    </div>
  )
}
