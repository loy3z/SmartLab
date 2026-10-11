import { useEffect, useState } from 'react'
import {
  cancelBooking,
  listApprovedBookings,
  listResources,
} from '../booking/api'
import type { Booking, Resource } from '../booking/types'

export function ManagerBookingsPage() {
  const [bookings, setBookings] = useState<Booking[]>([])
  const [rooms, setRooms] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [now, setNow] = useState(() => Date.now())

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

        const roomIds = new Set(resourceData.results.map((room) => room.id))

        setRooms(resourceData.results)
        setBookings(
          bookingData.results
            .filter((booking) => roomIds.has(booking.resource_id))
            .sort(
              (a, b) =>
                new Date(a.start).getTime() - new Date(b.start).getTime(),
            ),
        )
      } catch (err: unknown) {
        if (active) {
          setError(err instanceof Error ? err.message : 'Unable to load bookings.')
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

  async function handleCancel(booking: Booking, roomName: string) {
    if (busyId) return

    setError('')
    setSuccess('')

    if (new Date(booking.start).getTime() <= now) {
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
      setSuccess('Booking cancelled successfully. The time slot has been released.')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Cancellation failed.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <h1>Room booking management</h1>
      <p>View confirmed room bookings and cancel bookings that have not started.</p>

      <button
        type="button"
        disabled={loading || busyId !== null}
        onClick={() => {
          setSuccess('')
          setRefresh((value) => value + 1)
        }}
      >
        Refresh
      </button>

      {error && <p role="alert" className="bk-error">{error}</p>}
      {success && <p role="status">{success}</p>}
      {loading && <p>Loading bookings...</p>}

      {!loading && !error && bookings.length === 0 && (
        <p>No confirmed room bookings.</p>
      )}

      {!loading && (
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
                <h2>{roomName}</h2>
                <span className="bk-chip is-ok">Approved</span>

                <p><strong>Student ID: </strong>{booking.student_id}</p>
                <p>
                  <strong>Start: </strong>
                  {new Date(booking.start).toLocaleString()}
                </p>
                <p>
                  <strong>End: </strong>
                  {new Date(booking.end).toLocaleString()}
                </p>
                <p><strong>Purpose: </strong>{booking.purpose}</p>

                <button
                  type="button"
                  disabled={busyId !== null || started}
                  onClick={() => void handleCancel(booking, roomName)}
                >
                  {busyId === booking.id ? 'Cancelling...' : 'Cancel booking'}
                </button>

                {started && (
                  <p className="bk-muted">
                    This booking has started or ended and cannot be cancelled.
                  </p>
                )}
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
