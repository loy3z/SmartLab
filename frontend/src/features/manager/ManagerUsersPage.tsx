import { useEffect, useRef, useState } from 'react'
import {
  listManagerUsers,
  updateUserRole,
} from '../booking/api'
import { errorMessage } from '../booking/format'
import type { User } from '../booking/types'

const roleLabels = {
  STUDENT: 'Student',
  ADMIN: 'Admin',
  MANAGER: 'Manager',
}

export function ManagerUsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [refresh, setRefresh] = useState(0)

  const mounted = useRef(false)
  const saving = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
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
        setError('')
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [refresh])

  function reload() {
    setLoading(true)
    setError('')
    setSuccess('')
    setRefresh((value) => value + 1)
  }

  async function changeRole(user: User) {
    if (saving.current || user.role === 'MANAGER') return

    const nextRole = user.role === 'STUDENT' ? 'ADMIN' : 'STUDENT'

    const confirmed = window.confirm(
      `Change ${user.display_name} (${user.zid}) from ` +
      `${roleLabels[user.role]} to ${roleLabels[nextRole]}?`,
    )

    if (!confirmed) return

    saving.current = true
    setBusyId(user.id)
    setError('')
    setSuccess('')

    try {
      const updatedUser = await updateUserRole(user.id, nextRole)

      if (!mounted.current) return

      setUsers((current) =>
        current.map((item) =>
          item.id === updatedUser.id ? updatedUser : item,
        ),
      )
      setSuccess(
        `${updatedUser.zid} is now ${roleLabels[updatedUser.role]}.`,
      )
    } catch (err) {
      if (mounted.current) setError(errorMessage(err))
    } finally {
      saving.current = false
      if (mounted.current) setBusyId(null)
    }
  }

  return (
    <section className="app-card">
      <h1>User Management</h1>
      <p>
        View all users and change roles between Student and Admin.
      </p>

      <button
        type="button"
        className="app-button app-button-secondary"
        onClick={reload}
        disabled={loading || busyId !== null}
      >
        Refresh
      </button>

      {error && (
        <p role="alert" className="bk-error">{error}</p>
      )}
      {success && <p role="status">{success}</p>}

      {loading ? (
        <p role="status">Loading users...</p>
      ) : (
        <>
          <p>{users.length} users</p>

          {users.length === 0 && !error && (
            <p>No users found.</p>
          )}

          {users.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  textAlign: 'left',
                }}
              >
                <thead>
                  <tr>
                    {['zID', 'Name', 'Email', 'Role', 'Status', 'Action']
                      .map((heading) => (
                        <th
                          key={heading}
                          scope="col"
                          style={{
                            padding: 12,
                            borderBottom: '1px solid #ddd',
                          }}
                        >
                          {heading}
                        </th>
                      ))}
                  </tr>
                </thead>

                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td style={{ padding: 12 }}>{user.zid}</td>
                      <td style={{ padding: 12 }}>
                        {user.display_name}
                      </td>
                      <td style={{ padding: 12 }}>
                        {user.university_email || '—'}
                      </td>
                      <td style={{ padding: 12 }}>
                        {roleLabels[user.role]}
                      </td>
                      <td style={{ padding: 12 }}>
                        {user.active ? 'Active' : 'Inactive'}
                      </td>
                      <td style={{ padding: 12 }}>
                        {user.role === 'MANAGER' ? (
                          <span>—</span>
                        ) : (
                          <button
                            type="button"
                            className="app-button app-button-secondary"
                            disabled={busyId !== null || Boolean(error)}
                            onClick={() => changeRole(user)}
                            aria-label={
                              `Change ${user.zid} to ` +
                              (user.role === 'STUDENT' ? 'Admin' : 'Student')
                            }
                          >
                            {busyId === user.id
                              ? 'Saving...'
                              : user.role === 'STUDENT'
                                ? 'Make Admin'
                                : 'Make Student'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}