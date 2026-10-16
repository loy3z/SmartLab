import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { EmptyState, PageHeader, RefreshStamp, Tabs } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { createStaff, listManagerUsers, resetStaffAccess, setUserActive } from '../booking/api'
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

type StaffRole = 'ADMIN' | 'MANAGER'

const STAFF_HELP: Record<StaffRole, string> = {
  ADMIN: 'Admins review induction evidence and booking requests. Staff accounts do not book resources.',
  MANAGER: 'Managers can do everything an Admin can, and also manage users, resources and every booking.',
}

function InductionSummary({ user, now }: { user: ManagedUser; now: number }) {
  // Staff do not book, so inductions only matter for students.
  if (user.role !== 'STUDENT') return <span className="bk-muted">—</span>
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

/** Staff sign in on the staff page. Until they activate, show the invite code the Manager hands over. */
function StaffAccess({ user, onCopy }: { user: ManagedUser; onCopy: (code: string) => void }) {
  if (user.activation_status === 'ACTIVATED') return <span className="ui-pill is-green">Activated</span>
  return (
    <span className="um-invite">
      <span className="ui-pill is-amber">Awaiting activation</span>
      {user.invite_code && <>
        <code aria-label={`Invite code for ${user.zid}`}>{user.invite_code}</code>
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => onCopy(user.invite_code ?? '')}>Copy</button>
      </>}
    </span>
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
  const [refresh, setRefresh] = useState(0)
  const [adding, setAdding] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

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

  async function toggleActive(user: ManagedUser) {
    if (busyId) return
    const deactivate = user.active
    const answer = await feedback.confirm({
      title: deactivate ? `Deactivate ${user.display_name}?` : `Reactivate ${user.display_name}?`,
      details: [{ label: 'zID', value: user.zid }, { label: 'Role', value: ROLE_LABEL[user.role] }],
      message: !deactivate
        ? `They can sign in again as ${ROLE_LABEL[user.role]}.`
        : user.role === 'STUDENT'
          ? 'They can no longer sign in. Their requests that are awaiting approval or on the waitlist are rejected now and the time passes to the next person; approved bookings stay and can be reviewed in Room booking management.'
          : 'They can no longer sign in. Use this when someone leaves the role; add their replacement with Add staff.',
      confirmLabel: deactivate ? 'Deactivate' : 'Reactivate',
      danger: deactivate,
    })
    if (!answer.confirmed) return
    setBusyId(user.id)
    try {
      const updated = await setUserActive(user.id, !deactivate)
      setUsers((list) => list.map((item) => (item.id === updated.id ? updated : item)))
      feedback.success(`${updated.display_name} (${updated.zid}) ${updated.active ? 'can sign in again' : 'can no longer sign in'}.`,
        updated.active ? 'Account reactivated' : 'Account deactivated')
    } catch (err: unknown) {
      feedback.error(errorMessage(err), deactivate ? 'Not deactivated' : 'Not reactivated')
      reload()
    } finally {
      setBusyId(null)
    }
  }

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      feedback.success(`Invite code ${code} copied.`, 'Copied')
    } catch {
      feedback.error(`Copy it by hand: ${code}`, 'Could not copy')
    }
  }

  async function resetAccess(user: ManagedUser) {
    if (busyId) return
    const answer = await feedback.confirm({
      title: `Reset sign-in for ${user.display_name}?`,
      details: [{ label: 'zID', value: user.zid }, { label: 'Role', value: ROLE_LABEL[user.role] }],
      message: 'Their current password stops working and a new invite code is shown here. Give them the code; they choose a new password on the Staff sign-in page. Their role does not change.',
      confirmLabel: 'Reset access',
      danger: true,
    })
    if (!answer.confirmed) return
    setBusyId(user.id)
    try {
      const updated = await resetStaffAccess(user.id)
      setUsers((list) => list.map((item) => (item.id === updated.id ? updated : item)))
      feedback.success(`New invite code for ${updated.zid}: ${updated.invite_code}. It is also shown in the list.`, 'Access reset')
    } catch (err: unknown) {
      feedback.error(errorMessage(err), 'Access not reset')
      reload()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <PageHeader
        title="User Management"
        description="See every account. Students book resources; Admins review requests and evidence; Managers set the rules and manage people. Each role is fixed when the account is created: to replace someone, add the new account and deactivate the old one."
        actions={(
          <>
            <RefreshStamp at={loadedAt} onRefresh={reload} busy={loading && loadedAt !== null} />
            <button type="button" className="ui-btn ui-btn-primary" onClick={() => setAdding(true)}>+ Add staff</button>
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
              <tr><th>Name</th><th>zID</th><th className="ui-hide-sm">Email</th><th>Role</th><th>Induction / sign-in</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {rows.map((user) => {
                const self = me?.id === user.id
                return (
                  <tr key={user.id}>
                    <td>
                      <span className="ui-primary-text">{user.display_name || user.zid}</span>
                      {self && <span className="ui-sub-text">You</span>}
                    </td>
                    <td>{user.zid}</td>
                    <td className="ui-hide-sm">{user.university_email}</td>
                    <td>
                      <span className={`ui-pill ${ROLE_TONE[user.role]}`}>{ROLE_LABEL[user.role]}</span>
                      {!user.active && <> <span className="ui-pill is-red">Inactive</span></>}
                    </td>
                    <td>{user.is_staff ? <StaffAccess user={user} onCopy={(code) => void copyCode(code)} /> : <InductionSummary user={user} now={now} />}</td>
                    <td>
                      <div className="ui-actions">
                        {user.is_staff && !self && user.active && (
                          <button
                            type="button"
                            className="ui-btn ui-btn-ghost ui-btn-sm"
                            disabled={busyId !== null}
                            aria-label={`Reset access for ${user.zid}`}
                            onClick={() => void resetAccess(user)}
                          >
                            Reset access
                          </button>
                        )}
                        {!self && (
                          <button
                            type="button"
                            className="ui-btn ui-btn-ghost ui-btn-sm"
                            disabled={busyId !== null}
                            aria-label={`${user.active ? 'Deactivate' : 'Reactivate'} ${user.zid}`}
                            onClick={() => void toggleActive(user)}
                          >
                            {busyId === user.id ? 'Saving…' : user.active ? 'Deactivate' : 'Reactivate'}
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
        <AddStaffDialog
          onClose={() => setAdding(false)}
          onCreated={(created) => {
            setAdding(false)
            setUsers((list) => [...list, created].sort((a, b) => a.zid.localeCompare(b.zid)))
            feedback.success(`Give ${created.display_name} the invite code ${created.invite_code}. They activate their ${created.role === 'ADMIN' ? 'Admin' : 'Manager'} account on the Staff sign-in page; the code also stays in the list until then.`, 'Staff added')
          }}
        />
      )}
    </section>
  )
}

function AddStaffDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (user: ManagedUser) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [role, setRole] = useState<StaffRole>('ADMIN')
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
      onCreated(await createStaff({ zid: zid.trim().toLowerCase(), display_name: name.trim(), university_email: email.trim(), role }))
    } catch (err) {
      const e = err as { code?: string }
      setError(e?.code === 'USER_EXISTS' ? 'Someone with this zID already exists.' : errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="ui-dialog" aria-labelledby="add-staff-title" onCancel={(e) => { e.preventDefault(); onClose() }}>
      <form className="ui-dialog-card" onSubmit={submit}>
        <h2 id="add-staff-title">Add staff</h2>
        <p className="ui-dialog-message">Creates a new staff account and an invite code. They activate it on the Staff sign-in page by choosing a password. The role cannot be changed later: to replace someone, add a new account and deactivate the old one. Staff do not book resources, and existing student accounts cannot be turned into staff.</p>
        <label className="ui-field"><span>Role</span>
          <select value={role} onChange={(e) => setRole(e.target.value as StaffRole)}>
            <option value="ADMIN">Admin</option>
            <option value="MANAGER">Manager</option>
          </select>
        </label>
        <p className="bk-muted">{STAFF_HELP[role]}</p>
        <label className="ui-field"><span>zID</span><input required autoFocus value={zid} placeholder="z5123456" onChange={(e) => setZid(e.target.value)} /></label>
        <label className="ui-field"><span>Full name</span><input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="ui-field"><span>University email</span><input required type="email" maxLength={254} value={email} placeholder="z5123456@ad.unsw.edu.au" onChange={(e) => setEmail(e.target.value)} /></label>
        {error && <p className="bk-error" role="alert">{error}</p>}
        <div className="ui-dialog-actions">
          <button type="button" className="ui-btn ui-btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="ui-btn ui-btn-primary" disabled={busy || !zid.trim() || !name.trim() || !email.trim()}>{busy ? 'Adding…' : `Add ${role === 'ADMIN' ? 'admin' : 'manager'}`}</button>
        </div>
      </form>
    </dialog>
  )
}
