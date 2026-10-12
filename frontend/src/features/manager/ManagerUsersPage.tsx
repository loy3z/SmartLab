import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { EmptyState, PageHeader, RefreshStamp, Tabs } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { createManager, listManagerUsers, updateUserRole } from '../booking/api'
import { errorMessage, fmtDateTime } from '../booking/format'
import type { ManagedUser, Role, UserInduction } from '../booking/types'

type Filter = 'ALL' | Role

const ROLE_LABEL: Record<Role, string> = { STUDENT: 'Student', ADMIN: 'Admin', MANAGER: 'Manager' }
const ROLE_TONE: Record<Role, string> = { STUDENT: 'is-grey', ADMIN: 'is-blue', MANAGER: 'is-amber' }
const INDUCTION_LABEL: Record<UserInduction['status'], string> = {
  NOT_SUBMITTED: 'Not submitted', PENDING: 'Under review', VERIFIED: 'Verified', REJECTED: 'Rejected', EXPIRED: 'Expired',
}

const current = (item: UserInduction, now: number) =>
  item.status === 'VERIFIED' && (item.valid_until === null || Date.parse(item.valid_until) > now)

/** A student may become an Admin only when every induction is verified and current. */
function canPromote(user: ManagedUser, now: number): boolean {
  return Array.isArray(user.inductions) && user.inductions.length > 0 && user.inductions.every((item) => current(item, now))
}

function InductionSummary({ user, now }: { user: ManagedUser; now: number }) {
  if (user.role === 'MANAGER') return <span className="bk-muted">—</span>
  const items = user.inductions ?? []
  const ok = items.filter((item) => current(item, now)).length
  const tone = items.length && ok === items.length ? 'is-green' : ok ? 'is-amber' : 'is-grey'
  return (
    <details className="um-ind">
      <summary><span className={`ui-pill ${tone}`}>{ok}/{items.length} verified</span></summary>
      <ul>
        {items.map((item) => (
          <li key={item.requirement_id}>
            <span>{item.name}</span>
            <span className="bk-muted">
              {item.status === 'VERIFIED' && !current(item, now) ? 'Expired' : INDUCTION_LABEL[item.status]}
              {item.status === 'VERIFIED' && item.valid_until && current(item, now) ? ` · until ${fmtDateTime(item.valid_until).split(',')[0]}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}

export function ManagerUsersPage() {
  const feedback = useFeedback()
  const { user: me } = useAuth()
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [filter, setFilter] = useState<Filter>('ALL')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    let active = true
    listManagerUsers()
      .then((data) => {
        if (!active) return
        setUsers([...data.results].sort((a, b) => a.zid.localeCompare(b.zid)))
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
  const counts = useMemo(() => ({
    ALL: users.length,
    STUDENT: users.filter((u) => u.role === 'STUDENT').length,
    ADMIN: users.filter((u) => u.role === 'ADMIN').length,
    MANAGER: users.filter((u) => u.role === 'MANAGER').length,
  }), [users])

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return users.filter((u) => (filter === 'ALL' || u.role === filter) &&
      (!term || [u.zid, u.display_name, u.university_email].some((v) => v.toLowerCase().includes(term))))
  }, [users, filter, search])

  async function changeRole(user: ManagedUser) {
    if (busyId || user.role === 'MANAGER') return
    const nextRole = user.role === 'STUDENT' ? 'ADMIN' : 'STUDENT'
    if (nextRole === 'ADMIN' && !canPromote(user, Date.now())) {
      feedback.error(`${user.display_name} must have every induction verified and current before becoming an Admin.`, 'Cannot promote yet')
      return
    }
    const answer = await feedback.confirm({
      title: nextRole === 'ADMIN' ? `Make ${user.display_name} an Admin?` : `Change ${user.display_name} back to Student?`,
      details: [{ label: 'zID', value: user.zid }, { label: 'Email', value: user.university_email }],
      message: nextRole === 'ADMIN'
        ? 'Admins review induction evidence and booking requests. They can still book for themselves but cannot approve their own requests.'
        : 'They lose access to the review pages. Their bookings are kept.',
      confirmLabel: nextRole === 'ADMIN' ? 'Make Admin' : 'Change to Student',
      danger: nextRole === 'STUDENT',
    })
    if (!answer.confirmed) return
    setBusyId(user.id)
    try {
      const updated = await updateUserRole(user.id, nextRole)
      setUsers((list) => list.map((item) => (item.id === updated.id ? updated : item)))
      feedback.success(`${updated.display_name} (${updated.zid}) is now ${ROLE_LABEL[updated.role]}.`, 'Role updated')
    } catch (err: unknown) {
      feedback.error(errorMessage(err), 'Role not changed')
      reload()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <PageHeader
        title="User Management"
        description="See everyone's role and induction status. Promote trusted students to Admin, or add a new Manager."
        actions={(
          <>
            <RefreshStamp at={loadedAt} onRefresh={reload} busy={loading && loadedAt !== null} />
            <button type="button" className="ui-btn ui-btn-primary" onClick={() => setAdding(true)}>+ Add manager</button>
          </>
        )}
      />

      <div className="ui-toolbar">
        <Tabs
          label="Filter by role"
          value={filter}
          onChange={setFilter}
          items={[
            { key: 'ALL', label: 'Everyone', count: loadedAt ? counts.ALL : null },
            { key: 'STUDENT', label: 'Students', count: loadedAt ? counts.STUDENT : null },
            { key: 'ADMIN', label: 'Admins', count: loadedAt ? counts.ADMIN : null },
            { key: 'MANAGER', label: 'Managers', count: loadedAt ? counts.MANAGER : null },
          ]}
        />
        <div className="ui-filters">
          <input type="search" aria-label="Search users" placeholder="Search name, zID or email" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>

      {error && <p role="alert" className="bk-error">{error}</p>}
      {loading && loadedAt === null && <p role="status">Loading users…</p>}

      {loadedAt !== null && rows.length === 0 && <EmptyState icon="–" title="No users found">{search ? 'Try a different search.' : 'No one has this role yet.'}</EmptyState>}

      {rows.length > 0 && (
        <div className="ui-table-wrap">
          <table className="ui-table">
            <thead>
              <tr><th>Name</th><th>zID</th><th className="ui-hide-sm">Email</th><th>Role</th><th>Induction</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {rows.map((user) => {
                const blocked = user.role === 'STUDENT' && !canPromote(user, now)
                const self = me?.id === user.id
                return (
                  <tr key={user.id}>
                    <td>
                      <span className="ui-primary-text">{user.display_name || user.zid}</span>
                      {!user.active && <span className="ui-sub-text">Inactive account</span>}
                      {self && <span className="ui-sub-text">You</span>}
                    </td>
                    <td>{user.zid}</td>
                    <td className="ui-hide-sm">{user.university_email}</td>
                    <td><span className={`ui-pill ${ROLE_TONE[user.role]}`}>{ROLE_LABEL[user.role]}</span></td>
                    <td><InductionSummary user={user} now={now} /></td>
                    <td>
                      <div className="ui-actions">
                        {user.role === 'STUDENT' && (
                          <button
                            type="button"
                            className="ui-btn ui-btn-ghost ui-btn-sm"
                            disabled={busyId !== null || blocked}
                            title={blocked ? 'Every induction must be verified and current first.' : undefined}
                            aria-label={`Promote ${user.zid} to Admin`}
                            onClick={() => void changeRole(user)}
                          >
                            {busyId === user.id ? 'Saving…' : 'Make Admin'}
                          </button>
                        )}
                        {user.role === 'ADMIN' && (
                          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busyId !== null} aria-label={`Change ${user.zid} to Student`} onClick={() => void changeRole(user)}>
                            {busyId === user.id ? 'Saving…' : 'Change to Student'}
                          </button>
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

      {adding && (
        <AddManagerDialog
          onClose={() => setAdding(false)}
          onCreated={(created) => {
            setAdding(false)
            setUsers((list) => [...list, created].sort((a, b) => a.zid.localeCompare(b.zid)))
            feedback.success(`${created.display_name} (${created.zid}) can now sign in as a Manager.`, 'Manager added')
          }}
        />
      )}
    </section>
  )
}

function AddManagerDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (user: ManagedUser) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [zid, setZid] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    if (!/^[zZ]\d{7}$/.test(zid.trim())) return setError('zID must be z followed by 7 digits, e.g. z5123456.')
    setBusy(true)
    setError('')
    try {
      onCreated(await createManager({ zid: zid.trim().toLowerCase(), display_name: name.trim(), university_email: email.trim() }))
    } catch (err) {
      const e = err as { code?: string }
      setError(e?.code === 'USER_EXISTS' ? 'Someone with this zID already exists.' : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="ui-dialog" aria-labelledby="add-manager-title" onCancel={(e) => { e.preventDefault(); onClose() }}>
      <form className="ui-dialog-card" onSubmit={submit}>
        <h2 id="add-manager-title">Add a manager</h2>
        <p className="ui-dialog-message">Creates a new Manager account. Managers have every admin permission and can manage rooms and users.</p>
        <label className="ui-field"><span>zID</span><input required autoFocus value={zid} placeholder="z5123456" onChange={(e) => setZid(e.target.value)} /></label>
        <label className="ui-field"><span>Full name</span><input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="ui-field"><span>University email</span><input required type="email" maxLength={254} value={email} placeholder="z5123456@ad.unsw.edu.au" onChange={(e) => setEmail(e.target.value)} /></label>
        {error && <p className="bk-error" role="alert">{error}</p>}
        <div className="ui-dialog-actions">
          <button type="button" className="ui-btn ui-btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="ui-btn ui-btn-primary" disabled={busy || !zid.trim() || !name.trim() || !email.trim()}>{busy ? 'Adding…' : 'Add manager'}</button>
        </div>
      </form>
    </dialog>
  )
}
