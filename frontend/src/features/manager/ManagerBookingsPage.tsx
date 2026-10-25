import { useCallback, useEffect, useMemo, useState } from 'react'
import { EmptyState, PageHeader, RefreshStamp } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import {
  cancelBooking,
  listApprovedBookings,
  listResources,
  updateResourceStatus,
} from '../booking/api'
import { errorMessage, fmtDuration, fmtRange, minutesBetween } from '../booking/format'
import { Modal } from '../booking/Modal'
import { RescheduleBox } from '../booking/RescheduleBox'
import type { Booking, Resource, ResourceStatus } from '../booking/types'

const STATUS_LABELS: Record<ResourceStatus, string> = {
  AVAILABLE: 'Available',
  MAINTENANCE: 'Maintenance',
  CLOSED: 'Closed',
}
const STATUS_TONE: Record<ResourceStatus, string> = { AVAILABLE: 'is-green', MAINTENANCE: 'is-amber', CLOSED: 'is-red' }

/** Checked when the button is pressed (outside render, so the time is current). */
const hasStarted = (b: Booking) => Date.parse(b.start) <= Date.now()

const who = (b: Booking) => b.student?.display_name || b.student?.zid || b.student_id

export function ManagerBookingsPage() {
  const feedback = useFeedback()
  const [bookings, setBookings] = useState<Booking[]>([])
  const [rooms, setRooms] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [roomFilter, setRoomFilter] = useState('')
  const [moving, setMoving] = useState<Booking | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([listApprovedBookings(), listResources({ kind: 'ROOM' })])
      .then(([bookingData, resourceData]) => {
        if (!active) return
        const roomIds = new Set(resourceData.results.map((room) => room.id))
        setRooms(resourceData.results)
        setBookings(bookingData.results
          .filter((booking) => roomIds.has(booking.resource_id))
          .sort((a, b) => Date.parse(a.start) - Date.parse(b.start)))
        setLoadedAt(Date.now())
        setError('')
      })
      .catch((err: unknown) => active && setError(errorMessage(err)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [refresh])

  const reload = useCallback(() => {
    setLoading(true)
    setRefresh((value) => value + 1)
  }, [])

  const now = loadedAt ?? 0
  const roomName = (id: string) => rooms.find((room) => room.id === id)?.name ?? 'Room'
  const visibleBookings = useMemo(
    () => bookings.filter((b) => (!roomFilter || b.resource_id === roomFilter) && Date.parse(b.end) > now),
    [bookings, roomFilter, now],
  )

  async function changeStatus(room: Resource, status: ResourceStatus) {
    if (busy) return
    const affectedList = bookings.filter((b) => b.resource_id === room.id && Date.parse(b.end) > now)
    const upcoming = affectedList.length
    // Sprint 3 (1.16.0): say who is affected and that they are told automatically (site notice and email).
    const affectedDetails = affectedList.slice(0, 5).map((b) => ({ label: 'Booking', value: `${fmtRange(b.start, b.end)} · ${who(b)}${b.student?.zid ? ` (${b.student.zid})` : ''}` }))
    const answer = await feedback.confirm(status === 'AVAILABLE'
      ? {
        title: `Reopen ${room.name}?`,
        message: `Students can request it again. Waitlisted requests that now fit move to Awaiting approval.${upcoming ? ' People with bookings here are told it is open again.' : ''}`,
        confirmLabel: 'Reopen room',
      }
      : {
        title: `${status === 'MAINTENANCE' ? 'Put' : 'Close'} ${room.name}${status === 'MAINTENANCE' ? ' under maintenance' : ''}?`,
        message: `New requests and approvals stop. ${upcoming
          ? `${upcoming} confirmed booking${upcoming === 1 ? ' is' : 's are'} kept, and everyone with a booking or request here is told on the site and by email (with your reason). Afterwards, move or cancel the ones that cannot go ahead: they are marked in the list below.${upcoming > 5 ? ` First 5 of ${upcoming} shown.` : ''}`
          : 'There are no upcoming confirmed bookings.'}`,
        details: affectedDetails,
        reason: { label: 'Reason (shown to students)', placeholder: 'e.g. Fume hood repairs until Friday', maxLength: 500 },
        confirmLabel: status === 'MAINTENANCE' ? 'Start maintenance' : 'Close room',
        danger: true,
      })
    if (!answer.confirmed) return
    setBusy(room.id)
    try {
      const result = await updateResourceStatus(room.id, status, status === 'AVAILABLE' ? '' : answer.reason)
      const affected = result.affected_bookings.length
      feedback.success(
        result.resource.status === 'AVAILABLE'
          ? `${room.name} is open for requests again.`
          : `${room.name} is now ${STATUS_LABELS[result.resource.status].toLowerCase()}. ${affected ? `${affected} booking${affected === 1 ? '' : 's'} or request${affected === 1 ? '' : 's'} affected; the people were notified. Decide on each below.` : 'No bookings are affected.'}`,
        'Room status updated',
      )
    } catch (err: unknown) {
      feedback.error(errorMessage(err), 'Status not changed')
    } finally {
      setBusy(null)
      reload()
    }
  }

  async function handleCancel(booking: Booking) {
    if (busy) return
    if (hasStarted(booking)) {
      feedback.error('This booking has already started and cannot be cancelled.', 'Cannot cancel')
      return
    }
    const answer = await feedback.confirm({
      title: 'Cancel this booking?',
      details: [
        { label: 'Room', value: roomName(booking.resource_id) },
        { label: 'Student', value: `${who(booking)}${booking.student?.zid ? ` (${booking.student.zid})` : ''}` },
        { label: 'Time', value: fmtRange(booking.start, booking.end) },
      ],
      message: 'The time is released and offered to the waitlist. This cannot be undone.',
      confirmLabel: 'Cancel booking',
      cancelLabel: 'Keep booking',
      danger: true,
    })
    if (!answer.confirmed) return
    setBusy(booking.id)
    try {
      await cancelBooking(booking.id)
      feedback.success(`${roomName(booking.resource_id)} · ${fmtRange(booking.start, booking.end)}`, 'Booking cancelled')
    } catch (err: unknown) {
      feedback.error(errorMessage(err), 'Cancellation failed')
    } finally {
      setBusy(null)
      reload()
    }
  }

  return (
    <div>
      <PageHeader
        title="Room management"
        actions={<RefreshStamp at={loadedAt} onRefresh={reload} busy={loading && loadedAt !== null} />}
      />

      {error && <p role="alert" className="bk-error">{error}</p>}
      {loading && loadedAt === null && <p role="status">Loading rooms and bookings…</p>}

      {loadedAt !== null && (
        <>
          <h2 className="bk-h2">Rooms</h2>
          {rooms.length === 0 ? <EmptyState icon="–" title="No rooms found" /> : (
            <div className="ui-table-wrap">
              <table className="ui-table">
                <thead>
                  <tr><th>Room</th><th>Status</th><th className="ui-hide-sm">Reason</th><th className="ui-num">Upcoming</th><th><span className="sr-only">Actions</span></th></tr>
                </thead>
                <tbody>
                  {rooms.map((room) => (
                    <tr key={room.id}>
                      <td><span className="ui-primary-text">{room.name}</span><span className="ui-sub-text">{room.location}</span></td>
                      <td><span className={`ui-pill ${STATUS_TONE[room.status]}`}>{STATUS_LABELS[room.status]}</span></td>
                      <td className="ui-hide-sm">{room.status_reason || <span className="bk-muted">—</span>}</td>
                      <td className="ui-num">{bookings.filter((b) => b.resource_id === room.id && Date.parse(b.end) > now).length}</td>
                      <td>
                        <div className="ui-actions">
                          {room.status === 'AVAILABLE' ? (
                            <>
                              <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy !== null} onClick={() => void changeStatus(room, 'MAINTENANCE')}>Maintenance</button>
                              <button type="button" className="ui-btn ui-btn-reject ui-btn-sm" disabled={busy !== null} onClick={() => void changeStatus(room, 'CLOSED')}>Close</button>
                            </>
                          ) : (
                            <button type="button" className="ui-btn ui-btn-approve ui-btn-sm" disabled={busy !== null} onClick={() => void changeStatus(room, 'AVAILABLE')}>{busy === room.id ? 'Saving…' : 'Reopen'}</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="ui-toolbar" style={{ marginTop: 28 }}>
            <h2 className="bk-h2" style={{ margin: 0 }}>Upcoming confirmed bookings</h2>
            <div className="ui-filters">
              <select aria-label="Filter by room" value={roomFilter} onChange={(e) => setRoomFilter(e.target.value)}>
                <option value="">All rooms</option>
                {rooms.map((room) => <option key={room.id} value={room.id}>{room.name}</option>)}
              </select>
            </div>
          </div>
          {visibleBookings.length === 0 ? (
            <EmptyState icon="–" title="No upcoming confirmed bookings">Approved room bookings appear here.</EmptyState>
          ) : (
            <div className="ui-table-wrap">
              <table className="ui-table">
                <thead>
                  <tr><th>Time</th><th>Room</th><th>Student</th><th className="ui-hide-sm">Purpose</th><th><span className="sr-only">Actions</span></th></tr>
                </thead>
                <tbody>
                  {visibleBookings.map((booking) => {
                    const room = rooms.find((item) => item.id === booking.resource_id)
                    const started = Date.parse(booking.start) <= now
                    return (
                      <tr key={booking.id} className={room && room.status !== 'AVAILABLE' ? 'is-attention' : undefined}>{/* Sprint 3 (1.16.0) */}
                        <td>{fmtRange(booking.start, booking.end)}<span className="ui-sub-text">{fmtDuration(minutesBetween(booking.start, booking.end))}</span></td>
                        <td>
                          {room?.name ?? 'Room'}
                          {room && room.status !== 'AVAILABLE' && <span className="ui-sub-text" style={{ color: 'var(--red)' }}>Room {STATUS_LABELS[room.status].toLowerCase()}: keep, move or cancel</span>}
                        </td>
                        <td>
                          <span className="ui-primary-text">{who(booking)}</span><span className="ui-sub-text">{booking.student?.zid}</span>
                          {booking.on_behalf && booking.created_by_user && <span className="ui-sub-text">Booked by {booking.created_by_user.zid}</span>}
                          {booking.urgent && <span className="ui-badge-urgent">URGENT</span>}
                        </td>
                        <td className="ui-hide-sm">{booking.purpose}</td>
                        <td>
                          <div className="ui-actions">
                            <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy !== null || started || !room} title={started ? 'Already started' : undefined} onClick={() => setMoving(booking)}>
                              Reschedule
                            </button>
                            <button type="button" className="ui-btn ui-btn-reject ui-btn-sm" disabled={busy !== null || started} title={started ? 'Already started' : undefined} onClick={() => void handleCancel(booking)}>
                              {busy === booking.id ? 'Cancelling…' : 'Cancel'}
                            </button>
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

      {moving && rooms.some((room) => room.id === moving.resource_id) && (
        <Modal label="Reschedule booking" onClose={() => setMoving(null)}>
          <div className="bk-form">
            <h2>Reschedule booking</h2>
            <p className="bk-muted">
              {roomName(moving.resource_id)} · {who(moving)} ({moving.student?.zid}) · now {fmtRange(moving.start, moving.end)}.
              Only Managers can reschedule. The induction, opening-hours and conflict rules still apply; the minimum advance window does not.
            </p>
            <RescheduleBox
              booking={moving}
              resource={rooms.find((room) => room.id === moving.resource_id)!}
              onClose={() => setMoving(null)}
              onDone={(updated) => {
                setMoving(null)
                feedback.success(`New time: ${fmtRange(updated.start, updated.end)}.`, 'Booking moved')
                reload()
              }}
            />
          </div>
        </Modal>
      )}
    </div>
  )
}
