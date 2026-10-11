import { useEffect, useRef, useState } from 'react'
import {
  listManagerUsers,
  updateUserRole,
} from '../booking/api'
import { errorMessage } from '../booking/format'
import type { ManagedUser } from '../booking/types'

type ListRole = 'STUDENT' | 'ADMIN'

const inductionLabels = {
  NOT_SUBMITTED: 'Not submitted',
  PENDING: 'Pending review',
  VERIFIED: 'Verified',
  REJECTED: 'Rejected',
  EXPIRED: 'Expired',
}

function canPromote(user: ManagedUser, now: number): boolean {
  return (
    user.induction_status === 'VERIFIED' &&
    Array.isArray(user.inductions) &&
    user.inductions.length > 0 &&
    user.inductions.every(
      (item) =>
        item.status === 'VERIFIED' &&
        (
          item.valid_until === null ||
          Date.parse(item.valid_until) > now
        ),
    )
  )
}

export function ManagerUsersPage() {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [openList, setOpenList] = useState<ListRole | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [success, setSuccess] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [now, setNow] = useState(() => Date.now())

  const mounted = useRef(false)
  const saving = useRef(false)

  useEffect(() => {
    mounted.current = true

    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 15000)

    return () => {
      mounted.current = false
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let active = true

    listManagerUsers()
      .then((data) => {
        if (!active) return

        setUsers(
          [...data.results].sort((a, b) =>
            a.zid.localeCompare(b.zid),
          ),
        )
        setNow(Date.now())
        setLoadError('')
      })
      .catch((err: unknown) => {
        if (active) setLoadError(errorMessage(err))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [refresh])

  function reload() {
    if (saving.current || loading) return

    setLoading(true)
    setLoadError('')
    setActionError('')
    setSuccess('')
    setRefresh((value) => value + 1)
  }

  async function changeRole(user: ManagedUser) {
    if (
      saving.current ||
      loading ||
      loadError ||
      user.role === 'MANAGER'
    ) {
      return
    }

    setActionError('')
    setSuccess('')

    if (user.role === 'STUDENT' && !canPromote(user, Date.now())) {
      setActionError(
        'All induction checks must be verified and valid before promotion.',
      )
      return
    }

    const nextRole = user.role === 'STUDENT' ? 'ADMIN' : 'STUDENT'
    const nextLabel = nextRole === 'ADMIN' ? 'Admin' : 'Student'

    if (
      !window.confirm(
        `Change ${user.display_name} (${user.zid}) to ${nextLabel}?`,
      )
    ) {
      return
    }

    saving.current = true
    setBusyId(user.id)

    try {
      const updated = await updateUserRole(user.id, nextRole)

      if (!mounted.current) return

      setUsers((current) =>
        current.map((item) =>
          item.id === updated.id ? updated : item,
        ),
      )
      setSuccess(
        `${updated.display_name} (${updated.zid}) is now ${nextLabel}.`,
      )
    } catch (err: unknown) {
      if (mounted.current) setActionError(errorMessage(err))
    } finally {
      saving.current = false

      if (mounted.current) {
        setBusyId(null)
        setNow(Date.now())
      }
    }
  }

  const visibleUsers = users.filter((user) => user.role === openList)

  return (
    <section>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div>
          <h1 style={{ marginBottom: 8 }}>User Management</h1>
          <p className="bk-muted" style={{ margin: 0 }}>
            Select a list to view users and manage their roles.
          </p>
        </div>

        <button
          type="button"
          className="app-button app-button-secondary"
          onClick={reload}
          disabled={loading || busyId !== null}
        >
          Refresh
        </button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        {(['STUDENT', 'ADMIN'] as const).map((role) => {
          const selected = openList === role
          const count = users.filter((user) => user.role === role).length
          const label = role === 'STUDENT' ? 'Student List' : 'Admin List'

          return (
            <button
              key={role}
              type="button"
              aria-expanded={selected}
              aria-controls="user-list-panel"
              disabled={busyId !== null}
              onClick={() =>
                setOpenList((current) => current === role ? null : role)
              }
              style={{
                padding: '24px 20px',
                borderRadius: 14,
                border: selected
                  ? '2px solid #d6a700'
                  : '2px solid #e5e7eb',
                background: selected ? '#fff7d6' : '#fff',
                color: '#171717',
                textAlign: 'left',
                cursor: busyId !== null ? 'wait' : 'pointer',
                font: 'inherit',
              }}
            >
              <span
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <strong style={{ fontSize: 20 }}>{label}</strong>
                <span aria-hidden="true">{selected ? '▴' : '▾'}</span>
              </span>

              <span
                style={{
                  display: 'block',
                  marginTop: 8,
                  color: '#666',
                }}
              >
                {loading ? 'Loading...' : `${count} users`}
              </span>
            </button>
          )
        })}
      </div>

      {loadError && (
        <p role="alert" className="bk-error">{loadError}</p>
      )}

      {actionError && (
        <p role="alert" className="bk-error">{actionError}</p>
      )}

      {success && <p role="status">{success}</p>}

      <div id="user-list-panel">
        {openList === null ? (
          <p className="bk-muted">
            Click Student List or Admin List to expand.
          </p>
        ) : (
          <section className="app-card">
            <h2 style={{ marginTop: 0 }}>
              {openList === 'STUDENT' ? 'Students' : 'Administrators'}
            </h2>

            {openList === 'STUDENT' && (
              <p className="bk-muted">
                Students must pass all induction checks before becoming
                an Admin. Refresh after reviewing induction evidence.
              </p>
            )}

            {loading ? (
              <p role="status">Loading users...</p>
            ) : loadError ? (
              <p>Unable to load the list. Click Refresh to try again.</p>
            ) : visibleUsers.length === 0 ? (
              <p className="bk-muted">No users in this list.</p>
            ) : (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {visibleUsers.map((user) => {
                  const blocked =
                    user.role === 'STUDENT' && !canPromote(user, now)

                  return (
                    <li
                      key={user.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: 20,
                        padding: '22px 0',
                        borderBottom: '1px solid #e5e7eb',
                      }}
                    >
                      <div style={{ flex: '1 1 240px', minWidth: 0 }}>
                        <strong style={{ fontSize: 18 }}>
                          {user.display_name || user.zid}
                        </strong>

                        <p style={{ margin: '8px 0 4px' }}>
                          <b>zID:</b> {user.zid}
                        </p>

                        <p
                          style={{
                            margin: 0,
                            color: '#666',
                            overflowWrap: 'anywhere',
                          }}
                        >
                          <b>Email:</b> {user.university_email || '—'}
                        </p>

                        {!user.active && (
                          <p className="bk-muted">Inactive account</p>
                        )}

                        {blocked && (
                          <details style={{ marginTop: 12 }}>
                            <summary style={{ cursor: 'pointer' }}>
                              Induction incomplete — view details
                            </summary>

                            {user.inductions?.length ? (
                              <ul style={{ paddingLeft: 20 }}>
                                {user.inductions.map((item) => {
                                  const expired =
                                    item.status === 'VERIFIED' &&
                                    item.valid_until !== null &&
                                    !(
                                      Date.parse(item.valid_until) > now
                                    )

                                  return (
                                    <li key={item.requirement_id}>
                                      {item.name}: {' '}
                                      {expired
                                        ? 'Expired or invalid'
                                        : inductionLabels[item.status]}
                                    </li>
                                  )
                                })}
                              </ul>
                            ) : (
                              <p>No induction information available.</p>
                            )}
                          </details>
                        )}
                      </div>

                      <button
                        type="button"
                        className={
                          user.role === 'STUDENT'
                            ? 'app-button'
                            : 'app-button app-button-secondary'
                        }
                        disabled={busyId !== null || blocked}
                        onClick={() => changeRole(user)}
                        aria-label={
                          `${user.role === 'STUDENT' ? 'Promote' : 'Change'} ` +
                          `${user.zid} to ` +
                          (user.role === 'STUDENT' ? 'Admin' : 'Student')
                        }
                        title={
                          blocked
                            ? 'All inductions must be verified and valid.'
                            : undefined
                        }
                        style={{
                          flexShrink: 0,
                          opacity: blocked ? 0.5 : 1,
                          cursor: blocked ? 'not-allowed' : undefined,
                        }}
                      >
                        {busyId === user.id
                          ? 'Saving...'
                          : user.role === 'STUDENT'
                            ? 'Promote to Admin'
                            : 'Change to Student'}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        )}
      </div>
    </section>
  )
}