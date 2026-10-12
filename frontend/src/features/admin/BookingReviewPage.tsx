import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Drawer, EmptyState, Facts, InfoDisclosure, PageHeader, RefreshStamp, Tabs } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { listAdminBookings, listAdminQualifications, listResources, listStudentBookings, reviewBooking } from '../booking/api'
import { errorMessage, fmtDateTime, fmtDuration, fmtRange, fmtRelative, minutesBetween, STATUS_TEXT } from '../booking/format'
import type { Booking, Qualification, Resource } from '../booking/types'

type ReviewTab = 'PENDING_APPROVAL' | 'WAITLISTED'
const URGENT_MS = 2 * 60 * 60 * 1000

const overlaps = (a: Booking, b: Booking) =>
  a.resource_id === b.resource_id && a.id !== b.id && Date.parse(a.start) < Date.parse(b.end) && Date.parse(b.start) < Date.parse(a.end)

const who = (b: Booking) => b.student?.display_name || b.student?.zid || 'Unknown student'

export function BookingReviewPage() {
  const feedback = useFeedback()
  const { user } = useAuth()
  const [tab, setTab] = useState<ReviewTab>('PENDING_APPROVAL')
  const [pending, setPending] = useState<Booking[]>([])
  const [waitlisted, setWaitlisted] = useState<Booking[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [resourceFilter, setResourceFilter] = useState('')
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)

  // The server decides expiry, automatic decisions and promotion; poll to show them.
  useEffect(() => {
    const timer = window.setInterval(() => setRefresh((n) => n + 1), 15000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let active = true
    Promise.all([listAdminBookings('PENDING_APPROVAL'), listAdminBookings('WAITLISTED'), listResources({})])
      .then(([p, w, r]) => {
        if (!active) return
        setPending(p.results)
        setWaitlisted(w.results)
        setResources(r.results)
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

  const resourceName = useCallback((b: Booking) => b.resource_name ?? resources.find((r) => r.id === b.resource_id)?.name ?? 'Resource', [resources])
  const now = loadedAt ?? 0

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase()
    const list = (tab === 'PENDING_APPROVAL' ? pending : waitlisted).filter((b) =>
      (!resourceFilter || b.resource_id === resourceFilter) &&
      (!term || [b.student?.zid, b.student?.display_name, b.student?.university_email].some((v) => v?.toLowerCase().includes(term))))
    return [...list].sort((a, b) => tab === 'PENDING_APPROVAL'
      ? Date.parse(a.review_due_at ?? a.start) - Date.parse(b.review_due_at ?? b.start)
      : a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id))
  }, [tab, pending, waitlisted, resourceFilter, search])

  const open = [...pending, ...waitlisted].find((b) => b.id === openId) ?? null

  async function approve(b: Booking) {
    if (busy) return
    setBusy(b.id)
    try {
      await reviewBooking(b.id, 'APPROVED')
      feedback.success(`${who(b)} · ${resourceName(b)} · ${fmtRange(b.start, b.end)}`, 'Booking approved')
      setOpenId(null)
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not approve')
    } finally {
      setBusy(null)
      reload()
    }
  }

  async function reject(b: Booking) {
    if (busy) return
    const answer = await feedback.confirm({
      title: b.status === 'WAITLISTED' ? 'Reject this waitlisted request?' : 'Reject this request?',
      details: [
        { label: 'Student', value: `${who(b)}${b.student?.zid ? ` (${b.student.zid})` : ''}` },
        { label: 'Resource', value: resourceName(b) },
        { label: 'Time', value: fmtRange(b.start, b.end) },
      ],
      reason: { label: 'Reason (shown to the student)', placeholder: 'e.g. The lab is reserved for a class at that time.' },
      confirmLabel: 'Reject request',
      danger: true,
    })
    if (!answer.confirmed) return
    setBusy(b.id)
    try {
      await reviewBooking(b.id, 'REJECTED', answer.reason)
      feedback.success(`${who(b)} · ${resourceName(b)}. The student will see your reason.`, 'Request rejected')
      setOpenId(null)
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not reject')
    } finally {
      setBusy(null)
      reload()
    }
  }

  const own = (b: Booking) => Boolean(user && b.student_id === user.id)

  const actions = (b: Booking, size = 'ui-btn-sm') => own(b)
    ? <span className="bk-muted">Your own request</span>
    : (
      <>
        {b.status === 'PENDING_APPROVAL' && (
          <button type="button" className={`ui-btn ui-btn-approve ${size}`} disabled={busy !== null} onClick={(e) => { e.stopPropagation(); void approve(b) }}>
            {busy === b.id ? 'Saving…' : '✓ Approve'}
          </button>
        )}
        <button type="button" className={`ui-btn ui-btn-reject ${size}`} disabled={busy !== null} onClick={(e) => { e.stopPropagation(); void reject(b) }}>✕ Reject</button>
      </>
    )

  const blockerText = (b: Booking) => {
    const ahead = pending.find((p) => overlaps(p, b))
    return ahead ? `${who(ahead)}'s request (awaiting approval)` : 'An approved booking'
  }

  return (
    <>
      <PageHeader
        title="Booking Review"
        description="Approve or reject booking requests. Requests nearest their review deadline are listed first."
        actions={<RefreshStamp at={loadedAt} onRefresh={reload} busy={loading && loadedAt !== null} />}
      />

      <div className="ui-toolbar">
        <Tabs
          label="Request lists"
          value={tab}
          onChange={(next) => { setTab(next); setOpenId(null) }}
          items={[
            { key: 'PENDING_APPROVAL', label: 'Awaiting approval', count: loadedAt ? pending.length : null },
            { key: 'WAITLISTED', label: 'Waitlisted', count: loadedAt ? waitlisted.length : null },
          ]}
        />
        <div className="ui-filters">
          <select aria-label="Filter by resource" value={resourceFilter} onChange={(e) => setResourceFilter(e.target.value)}>
            <option value="">All resources</option>
            {resources.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          <input type="search" aria-label="Search students" placeholder="Search student name or zID" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>

      <InfoDisclosure summary="How approval works">
        <ul>
          <li>Every request waits here for an admin. It holds its time until you decide.</li>
          <li>If nobody decides before the deadline, the system approves it when the student's induction is still valid and the time is free, and rejects it otherwise.</li>
          <li>Requests for a time that is already taken are <b>waitlisted</b>. When the time frees up, the next one moves to Awaiting approval. Waitlisted requests can only be rejected.</li>
          <li>Admins cannot decide their own requests.</li>
        </ul>
      </InfoDisclosure>

      {loadError && <p className="bk-error" role="alert">{loadError}</p>}
      {loading && loadedAt === null && <p role="status">Loading requests…</p>}

      {loadedAt !== null && rows.length === 0 && (
        <EmptyState title={tab === 'PENDING_APPROVAL' ? "You're all caught up" : 'No one is waitlisted'}>
          {resourceFilter || search
            ? 'No requests match these filters.'
            : tab === 'PENDING_APPROVAL' ? 'There are no requests waiting for approval.' : 'Requests appear here when someone asks for a time that is already taken.'}
        </EmptyState>
      )}

      {rows.length > 0 && (
        <div className="ui-table-wrap">
          <table className="ui-table">
            <thead>
              <tr>
                <th>{tab === 'PENDING_APPROVAL' ? 'Decide within' : 'Queue'}</th>
                <th>Student</th>
                <th>Resource</th>
                <th>Time</th>
                {tab === 'WAITLISTED' && <th className="ui-hide-sm">Waiting behind</th>}
                <th className="ui-hide-sm">Submitted</th>
                <th><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => {
                const due = b.review_due_at ? Date.parse(b.review_due_at) : null
                const urgent = due !== null && due - now < URGENT_MS
                return (
                  <tr key={b.id} className={`is-clickable${openId === b.id ? ' is-selected' : ''}`} onClick={() => setOpenId(b.id)}>
                    <td>
                      {tab === 'PENDING_APPROVAL'
                        ? <span className={`ui-deadline${urgent ? ' is-urgent' : ''}`} title={b.review_due_at ? fmtDateTime(b.review_due_at) : ''}>{b.review_due_at ? fmtRelative(b.review_due_at, now).replace(/^in /, '') : '—'}</span>
                        : <span className="ui-pill is-amber">#{b.waitlist_position ?? '?'}</span>}
                    </td>
                    <td>
                      <span className="ui-primary-text">{who(b)}</span>
                      <span className="ui-sub-text">{b.student?.zid}{own(b) ? ' · you' : ''}</span>
                    </td>
                    <td>{resourceName(b)}</td>
                    <td>
                      {fmtRange(b.start, b.end)}
                      <span className="ui-sub-text">{fmtDuration(minutesBetween(b.start, b.end))}</span>
                    </td>
                    {tab === 'WAITLISTED' && <td className="ui-hide-sm">{blockerText(b)}</td>}
                    <td className="ui-hide-sm">{fmtRelative(b.created_at, now)}</td>
                    <td><div className="ui-actions">{actions(b)}</div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {open && (
        <BookingDrawer
          booking={open}
          resource={resources.find((r) => r.id === open.resource_id)}
          resourceName={resourceName(open)}
          waitingBehind={waitlisted.filter((w) => overlaps(w, open)).length}
          blocker={open.status === 'WAITLISTED' ? blockerText(open) : ''}
          now={now}
          onClose={() => setOpenId(null)}
          footer={actions(open, '')}
        />
      )}
    </>
  )
}

function BookingDrawer({ booking: b, resource, resourceName, waitingBehind, blocker, now, onClose, footer }: {
  booking: Booking
  resource?: Resource
  resourceName: string
  waitingBehind: number
  blocker: string
  now: number
  onClose: () => void
  footer: ReactNode
}) {
  const [induction, setInduction] = useState<Qualification | null | undefined>(undefined)
  const [others, setOthers] = useState<Booking[] | null>(null)

  useEffect(() => {
    let active = true
    const requirement = resource?.required_qualification_id
    listAdminQualifications('VERIFIED')
      .then((data) => {
        if (!active) return
        const mine = data.results
          .filter((q) => q.student_id === b.student_id && q.requirement_id === requirement)
          .sort((x, y) => y.submitted_at.localeCompare(x.submitted_at))[0]
        setInduction(mine ?? null)
      })
      .catch(() => active && setInduction(null))
    listStudentBookings(b.student_id)
      .then((data) => active && setOthers(data.results.filter((x) => x.id !== b.id && Date.parse(x.end) > Date.now() && ['APPROVED', 'PENDING_APPROVAL', 'WAITLISTED'].includes(x.status))))
      .catch(() => active && setOthers([]))
    return () => { active = false }
  }, [b.id, b.student_id, resource?.required_qualification_id])

  const inductionText = induction === undefined
    ? 'Checking…'
    : induction && induction.effective_status === 'VERIFIED'
      ? `Verified${induction.valid_until ? ` · valid until ${fmtDateTime(induction.valid_until)}` : ''}`
      : 'No valid induction for this resource'

  return (
    <Drawer
      title={b.student?.display_name || 'Booking request'}
      subtitle={`${b.student?.zid ?? ''}${b.student?.university_email ? ` · ${b.student.university_email}` : ''}`}
      onClose={onClose}
      footer={footer}
    >
      <section>
        <h3>Request</h3>
        <Facts items={[
          { label: 'Status', value: STATUS_TEXT[b.status] + (b.status === 'WAITLISTED' && b.waitlist_position ? ` · #${b.waitlist_position}` : '') },
          { label: 'Resource', value: resourceName },
          { label: 'Time', value: fmtRange(b.start, b.end) },
          { label: 'Length', value: fmtDuration(minutesBetween(b.start, b.end)) },
          { label: 'Purpose', value: b.purpose || '—' },
          { label: 'Submitted', value: fmtDateTime(b.created_at) },
          ...(b.status === 'PENDING_APPROVAL' && b.review_due_at
            ? [{ label: 'Decide by', value: `${fmtDateTime(b.review_due_at)} (${fmtRelative(b.review_due_at, now)})` }]
            : []),
          ...(blocker ? [{ label: 'Waiting behind', value: blocker }] : []),
          { label: 'Also waiting', value: waitingBehind ? `${waitingBehind} other request${waitingBehind === 1 ? '' : 's'} for this time` : 'Nobody else' },
        ]} />
      </section>
      <section>
        <h3>Induction</h3>
        <p className={induction && induction.effective_status === 'VERIFIED' ? 'bk-ok' : induction === null ? 'bk-error' : 'bk-muted'}>{inductionText}</p>
      </section>
      <section>
        <h3>Student's other upcoming bookings</h3>
        {others === null ? <p className="bk-muted">Loading…</p> : others.length === 0 ? <p className="bk-muted">None.</p> : (
          <ul className="ui-mini-list">
            {others.slice(0, 6).map((o) => (
              <li key={o.id}><span>{o.resource_name ?? 'Resource'} · {fmtRange(o.start, o.end)}</span><span className="bk-muted">{STATUS_TEXT[o.status]}</span></li>
            ))}
          </ul>
        )}
      </section>
    </Drawer>
  )
}
