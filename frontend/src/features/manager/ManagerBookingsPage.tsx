import { useEffect, useState } from 'react'
import {
  cancelBooking,
  downloadAllBookings,
  downloadUserBookings,
  listApprovedBookings,
  listResources,
  updateResourceStatus,
} from '../booking/api'
import type {
  Booking,
  Resource,
  ResourceStatus,
} from '../booking/types'

const STATUS_LABELS: Record<ResourceStatus, string> = {
  AVAILABLE: 'Available',
  MAINTENANCE: 'Maintenance',
  CLOSED: 'Closed',
}

interface RoomDraft {
  status: ResourceStatus
  reason: string
}

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

export function ManagerBookingsPage() {
  const [bookings, setBookings] = useState<Booking[]>([])
  const [rooms, setRooms] = useState<Resource[]>([])
  const [drafts, setDrafts] = useState<Record<string, RoomDraft>>({})
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [savingRoomId, setSavingRoomId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState('')
  const [downloadingUserId, setDownloadingUserId] =
    useState<string | null>(null)

  const actionBusy =
    loading || busyId !== null || savingRoomId !== null

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let active = true

    async function load() {
      setLoading(true)
      setError('')

      try {
        const [bookingData, resourceData] = await Promise.all([
          listApprovedBookings(),
          listResources({ kind: 'ROOM' }),
        ])

        if (!active) return

        const roomIds = new Set(
          resourceData.results.map((room) => room.id),
        )

        setRooms(resourceData.results)
        setBookings(
          bookingData.results
            .filter((booking) => roomIds.has(booking.resource_id))
            .sort(
              (a, b) =>
                new Date(a.start).getTime() -
                new Date(b.start).getTime(),
            ),
        )
      } catch (err: unknown) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : 'Unable to load rooms and bookings.',
          )
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    void load()

    return () => {
      active = false
    }
  }, [refresh])

  function updateDraft(room: Resource, patch: Partial<RoomDraft>) {
    setDrafts((previous) => {
      const current = previous[room.id] ?? {
        status: room.status,
        reason: room.status_reason ?? '',
      }

      return {
        ...previous,
        [room.id]: {
          ...current,
          ...patch,
        },
      }
    })
  }

  async function handleSaveRoom(room: Resource) {
    if (actionBusy) return

    const draft = drafts[room.id] ?? {
      status: room.status,
      reason: room.status_reason ?? '',
    }
    const reason =
      draft.status === 'AVAILABLE' ? '' : draft.reason.trim()

    setError('')
    setSuccess('')

    if (draft.status !== 'AVAILABLE' && !reason) {
      setError(`Please enter a reason for changing ${room.name}'s status.`)
      return
    }

    setSavingRoomId(room.id)

    try {
      const result = await updateResourceStatus(
        room.id,
        draft.status,
        reason,
      )

      setRooms((previous) =>
        previous.map((item) =>
          item.id === room.id ? result.resource : item,
        ),
      )

      setDrafts((previous) => {
        const next = { ...previous }
        delete next[room.id]
        return next
      })

      const message =
        result.resource.status === 'AVAILABLE'
          ? 'The room is open again. Eligible waitlisted requests may be automatically approved.'
          : `Existing bookings are kept. ${result.affected_bookings.length} active requests or bookings may be affected.`

      setSuccess(
        `${room.name}: ${STATUS_LABELS[result.resource.status]}. ${message}`,
      )

      // Reload because reopening may approve waitlisted bookings.
      setRefresh((value) => value + 1)
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to update room status.',
      )
    } finally {
      setSavingRoomId(null)
    }
  }

  async function handleCancel(booking: Booking, roomName: string) {
    if (actionBusy) return

    setError('')
    setSuccess('')

    if (new Date(booking.start).getTime() <= Date.now()) {
      setError('This booking has already started and cannot be cancelled.')
      return
    }

    const confirmed = window.confirm(
      `Cancel this booking?\n\nRoom: ${roomName}\nStudent ID: ${
        booking.student_id
      }\nStart: ${new Date(booking.start).toLocaleString()}`,
    )

    if (!confirmed) return

    setBusyId(booking.id)

    try {
      await cancelBooking(booking.id)

      setBookings((previous) =>
        previous.filter((item) => item.id !== booking.id),
      )
      setSuccess(
        'Booking cancelled successfully. Eligible waitlisted requests may be automatically approved.',
      )
      setRefresh((value) => value + 1)
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Cancellation failed.',
      )
    } finally {
      setBusyId(null)
    }
  }

  async function handleDownload() {
    if (downloading) return

    setDownloading(true)
    setDownloadError('')

    try {
      const blob = await downloadAllBookings()
      saveCsv(blob, 'smartlab-all-bookings.csv')
    } catch (err: unknown) {
      setDownloadError(
        err instanceof Error
          ? err.message
          : 'Unable to download bookings. Please try again.',
      )
    } finally {
      setDownloading(false)
    }
  }

  async function handleDownloadUser(studentId: string) {
    if (downloadingUserId !== null) return

    setDownloadingUserId(studentId)
    setDownloadError('')

    try {
      const blob = await downloadUserBookings(studentId)
      saveCsv(blob, `smartlab-user-${studentId}-bookings.csv`)
    } catch (err: unknown) {
      setDownloadError(
        err instanceof Error
          ? err.message
          : 'Unable to download bookings for this user.',
      )
    } finally {
      setDownloadingUserId(null)
    }
  }

  return (
    <div>
      <h1>Room booking management</h1>
      <p>Manage room availability and confirmed bookings.</p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        <button
          type="button"
          className="app-button"
          disabled={actionBusy}
          onClick={() => {
            setSuccess('')
            setRefresh((value) => value + 1)
          }}
        >
          Refresh
        </button>

        <button
          type="button"
          className="app-button"
          disabled={downloading || actionBusy}
          onClick={() => void handleDownload()}
        >
          {downloading ? 'Downloading...' : 'Download All Bookings'}
        </button>
      </div>

      <p className="bk-muted">
        Download room and equipment bookings for all users, including
        all statuses, as a CSV file.
      </p>

      {downloadError && (
        <p role="alert" className="bk-error">{downloadError}</p>
      )}
      {error && <p role="alert" className="bk-error">{error}</p>}
      {success && <p role="status">{success}</p>}
      {loading && <p>Loading rooms and bookings...</p>}

      {!loading && (
        <>
          <h2 style={{ marginTop: 28 }}>Room status management</h2>
          <p className="bk-muted">
            Maintenance and Closed stop new bookings and approvals.
            Existing bookings are kept until cancelled.
          </p>

          {rooms.length === 0 && !error && <p>No rooms found.</p>}

          <div style={{ display: 'grid', gap: 16 }}>
            {rooms.map((room) => {
              const draft = drafts[room.id] ?? {
                status: room.status,
                reason: room.status_reason ?? '',
              }

              const reasonRequired = draft.status !== 'AVAILABLE'
              const nextReason = reasonRequired ? draft.reason.trim() : ''
              const changed =
                draft.status !== room.status ||
                nextReason !== (room.status_reason ?? '')

              return (
                <section
                  key={room.id}
                  className="bk-bcard"
                  style={{ padding: 20 }}
                >
                  <h3>{room.name}</h3>
                  <p className="bk-muted">{room.location}</p>

                  <p>
                    <strong>Current status: </strong>
                    <span
                      className={`bk-chip ${
                        room.status === 'AVAILABLE' ? 'is-ok' : 'is-warn'
                      }`}
                    >
                      {STATUS_LABELS[room.status]}
                    </span>
                  </p>

                  {room.status_reason && (
                    <p>
                      <strong>Current reason: </strong>
                      {room.status_reason}
                    </p>
                  )}

                  <form
                    onSubmit={(event) => {
                      event.preventDefault()
                      void handleSaveRoom(room)
                    }}
                    style={{ display: 'grid', gap: 12, maxWidth: 560 }}
                  >
                    <label htmlFor={`status-${room.id}`}>New status</label>
                    <select
                      id={`status-${room.id}`}
                      value={draft.status}
                      disabled={actionBusy}
                      onChange={(event) =>
                        updateDraft(room, {
                          status: event.target.value as ResourceStatus,
                        })
                      }
                      style={{ padding: 10, width: '100%' }}
                    >
                      <option value="AVAILABLE">Available</option>
                      <option value="MAINTENANCE">Maintenance</option>
                      <option value="CLOSED">Closed</option>
                    </select>

                    {reasonRequired && (
                      <>
                        <label htmlFor={`reason-${room.id}`}>
                          Reason (required)
                        </label>
                        <textarea
                          id={`reason-${room.id}`}
                          value={draft.reason}
                          required
                          maxLength={500}
                          rows={3}
                          disabled={actionBusy}
                          placeholder="For example: Air conditioning repairs."
                          onChange={(event) =>
                            updateDraft(room, { reason: event.target.value })
                          }
                          style={{
                            padding: 10,
                            width: '100%',
                            boxSizing: 'border-box',
                            resize: 'vertical',
                          }}
                        />
                      </>
                    )}

                    <button
                      type="submit"
                      className="app-button"
                      disabled={
                        actionBusy ||
                        !changed ||
                        (reasonRequired && !draft.reason.trim())
                      }
                      style={{ justifySelf: 'start' }}
                    >
                      {savingRoomId === room.id ? 'Saving...' : 'Save status'}
                    </button>
                  </form>
                </section>
              )
            })}
          </div>

          <h2 style={{ marginTop: 32 }}>Confirmed room bookings</h2>

          {bookings.length === 0 && !error && (
            <p>No confirmed room bookings.</p>
          )}

          <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
            {bookings.map((booking) => {
              const room = rooms.find(
                (item) => item.id === booking.resource_id,
              )
              const roomName = room?.name ?? booking.resource_id
              const started = new Date(booking.start).getTime() <= now

              return (
                <section
                  key={booking.id}
                  className="bk-bcard"
                  style={{ padding: 20 }}
                >
                  <h3>{roomName}</h3>
                  <span className="bk-chip is-ok">Approved</span>

                  {room && room.status !== 'AVAILABLE' && (
                    <p className="bk-error">
                      Room status: {STATUS_LABELS[room.status]}.
                      This booking has not been automatically cancelled.
                    </p>
                  )}

                  <p>
                    <strong>Student ID: </strong>{booking.student_id}
                  </p>
                  <p>
                    <strong>Start: </strong>
                    {new Date(booking.start).toLocaleString()}
                  </p>
                  <p>
                    <strong>End: </strong>
                    {new Date(booking.end).toLocaleString()}
                  </p>
                  <p><strong>Purpose: </strong>{booking.purpose}</p>

                  <div
                    style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}
                  >
                    <button
                      type="button"
                      className="app-button"
                      disabled={actionBusy || started}
                      onClick={() => void handleCancel(booking, roomName)}
                    >
                      {busyId === booking.id
                        ? 'Cancelling...'
                        : 'Cancel booking'}
                    </button>

                    <button
                      type="button"
                      className="app-button"
                      disabled={downloadingUserId !== null || actionBusy}
                      onClick={() =>
                        void handleDownloadUser(booking.student_id)
                      }
                    >
                      {downloadingUserId === booking.student_id
                        ? 'Downloading...'
                        : 'Download User Bookings'}
                    </button>
                  </div>

                  {started && (
                    <p className="bk-muted">
                      This booking has started or ended and cannot be cancelled.
                    </p>
                  )}
                </section>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}