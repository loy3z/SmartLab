// Sprint 3: usage statistics tab of Booking Records (Admin and Manager). The figures are worked out by the backend
// (booking/services/reports.py).
import { useEffect, useMemo, useState } from 'react'
import { EmptyState } from '../../ui/components'
import { getUsageReport } from '../../api/index.ts'
import { errorMessage, todaySydney } from '../booking/format'
import type { UsageReport } from '../../api/types/index.ts'
import { lastFourWeeks, percent, sortUsage } from '../manager/usage'

export function UsageTab() {
  const initial = useMemo(() => lastFourWeeks(todaySydney()), [])
  const [first, setFirst] = useState(initial.first)
  const [last, setLast] = useState(initial.last)
  const [report, setReport] = useState<UsageReport | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    getUsageReport(first, last)
      .then((data) => { if (active) { setReport(data); setError('') } })
      .catch((e: unknown) => active && (setReport(null), setError(errorMessage(e))))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [first, last])

  const rows = report ? sortUsage(report.results) : []
  return (
    <section aria-label="Usage statistics">
      <div className="ui-toolbar">
        <div className="ui-filters">
          <label>From <input type="date" aria-label="From" value={first} max={last} onChange={(e) => e.target.value && setFirst(e.target.value)} /></label>
          <label>To <input type="date" aria-label="To" value={last} min={first} onChange={(e) => e.target.value && setLast(e.target.value)} /></label>
        </div>
        <button type="button" className="ui-btn ui-btn-ghost" onClick={() => window.print()}>Print</button>
      </div>
      <p className="bk-muted rec-note">
        How much each room and piece of equipment was booked, and whether people turned up. Attendance counts approved
        bookings that have already ended; bookings from before check-in existed are listed as not tracked.
      </p>
      {error && <p role="alert" className="bk-error">{error}</p>}
      {loading && !report && <p role="status">Loading the report…</p>}
      {report && rows.length === 0 && <EmptyState icon="–" title="No resources">Add rooms and equipment on the Resources page.</EmptyState>}
      {report && rows.length > 0 && (
        <>
          <div className="ui-filters" aria-label="Totals">
            <span className="ui-pill is-blue">{report.totals.approved} approved bookings</span>
            <span className="ui-pill is-blue">{report.totals.booked_hours} hours booked</span>
            <span className="ui-pill is-green">Attendance {percent(report.totals.attendance_rate)}</span>
            <span className="ui-pill is-red">{report.totals.no_show} missed</span>
          </div>
          <div className="ui-table-wrap">
            <table className="ui-table" aria-label="Usage by resource">
              <thead>
                <tr>
                  <th>Resource</th><th>Approved</th><th>Hours booked</th><th className="ui-hide-sm">Use of opening hours</th>
                  <th>Attendance</th><th className="ui-hide-sm">Missed</th><th className="ui-hide-sm">Cancelled / rejected</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.resource_id}>
                    <td>
                      <span className="ui-primary-text">{row.name}</span>
                      <span className="ui-sub-text">
                        {[row.kind === 'ROOM' ? 'Room' : row.room_name, row.category, row.active ? null : 'archived'].filter(Boolean).join(' · ')}
                      </span>
                    </td>
                    <td>{row.approved}</td>
                    <td>{row.booked_hours}</td>
                    <td className="ui-hide-sm">{percent(row.utilisation)}</td>
                    <td>{percent(row.attendance_rate)}{row.not_tracked ? <span className="ui-sub-text">{row.not_tracked} not tracked</span> : null}</td>
                    <td className="ui-hide-sm">{row.no_show}</td>
                    <td className="ui-hide-sm">{row.cancelled} / {row.rejected}</td>
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
