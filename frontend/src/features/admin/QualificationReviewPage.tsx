import { useCallback, useEffect, useMemo, useState } from 'react'
import { Drawer, EmptyState, Facts, InfoDisclosure, PageHeader, RefreshStamp, Tabs } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { listAdminQualifications, listRequirements, reviewQualification } from '../booking/api'
import { errorMessage, fmtDateTime, fmtRelative } from '../booking/format'
import type { Qualification, Requirement } from '../booking/types'
import { EvidencePreview } from '../induction/EvidencePreview'

type Tab = 'PENDING' | 'VERIFIED' | 'REJECTED'

const who = (q: Qualification) => q.student?.display_name || q.student?.zid || 'Unknown student'

export function QualificationReviewPage() {
  const feedback = useFeedback()
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('PENDING')
  const [lists, setLists] = useState<Record<Tab, Qualification[]>>({ PENDING: [], VERIFIED: [], REJECTED: [] })
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setInterval(() => setRefresh((n) => n + 1), 30000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let active = true
    Promise.all([listAdminQualifications('PENDING'), listAdminQualifications('VERIFIED'), listAdminQualifications('REJECTED'), listRequirements()])
      .then(([p, v, r, reqs]) => {
        if (!active) return
        setLists({ PENDING: p.results, VERIFIED: v.results, REJECTED: r.results })
        setRequirements(reqs.results)
        setLoadedAt(Date.now())
        setError('')
      })
      .catch((e: unknown) => active && setError(errorMessage(e)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [refresh])

  const reload = useCallback(() => {
    setLoading(true)
    setRefresh((n) => n + 1)
  }, [])

  const requirementName = (q: Qualification) => requirements.find((r) => r.id === q.requirement_id)?.name ?? 'Induction'
  const now = loadedAt ?? 0
  const own = (q: Qualification) => Boolean(user && q.student_id === user.id)

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return lists[tab]
      .filter((q) => !term || [q.student?.zid, q.student?.display_name, q.student?.university_email, q.title].some((v) => v?.toLowerCase().includes(term)))
      .sort((a, b) => tab === 'PENDING'
        ? a.submitted_at.localeCompare(b.submitted_at)
        : (b.reviewed_at ?? b.submitted_at).localeCompare(a.reviewed_at ?? a.submitted_at))
  }, [lists, tab, search])

  const open = Object.values(lists).flat().find((q) => q.id === openId) ?? null

  async function verify(q: Qualification) {
    if (busy) return
    const answer = await feedback.confirm({
      title: 'Verify this induction?',
      details: [
        { label: 'Student', value: `${who(q)}${q.student?.zid ? ` (${q.student.zid})` : ''}` },
        { label: 'Training', value: requirementName(q) },
      ],
      message: 'The student can then request bookings for the resources it covers until it expires.',
      confirmLabel: 'Verify',
    })
    if (!answer.confirmed) return
    setBusy(q.id)
    try {
      const result = await reviewQualification(q.id, 'VERIFIED')
      const until = result.submission.valid_until ? ` Valid until ${fmtDateTime(result.submission.valid_until)}.` : ''
      feedback.success(`${who(q)} · ${requirementName(q)}.${until}`, 'Induction verified')
      setOpenId(null)
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not verify')
    } finally {
      setBusy(null)
      reload()
    }
  }

  async function reject(q: Qualification) {
    if (busy) return
    const answer = await feedback.confirm({
      title: 'Reject this evidence?',
      details: [
        { label: 'Student', value: `${who(q)}${q.student?.zid ? ` (${q.student.zid})` : ''}` },
        { label: 'Training', value: requirementName(q) },
      ],
      message: "The student's undecided booking requests for these resources are rejected too.",
      reason: { label: 'Reason (shown to the student)', placeholder: 'e.g. The certificate is unreadable. Please upload a clearer scan.' },
      confirmLabel: 'Reject evidence',
      danger: true,
    })
    if (!answer.confirmed) return
    setBusy(q.id)
    try {
      const result = await reviewQualification(q.id, 'REJECTED', answer.reason)
      const cascaded = result.updated_bookings.length
      feedback.success(`${who(q)} · ${requirementName(q)}.${cascaded ? ` ${cascaded} booking request${cascaded === 1 ? ' was' : 's were'} rejected with it.` : ''}`, 'Evidence rejected')
      setOpenId(null)
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not reject')
    } finally {
      setBusy(null)
      reload()
    }
  }

  const actions = (q: Qualification, size = 'ui-btn-sm') => {
    if (q.status !== 'PENDING') return null
    if (own(q)) return <span className="bk-muted">Your own evidence</span>
    return (
      <>
        <button type="button" className={`ui-btn ui-btn-approve ${size}`} disabled={busy !== null} onClick={(e) => { e.stopPropagation(); void verify(q) }}>
          {busy === q.id ? 'Saving…' : '✓ Verify'}
        </button>
        <button type="button" className={`ui-btn ui-btn-reject ${size}`} disabled={busy !== null} onClick={(e) => { e.stopPropagation(); void reject(q) }}>✕ Reject</button>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Induction qualification review"
        description="Check each student's training evidence. Open a row to see the file."
        actions={<RefreshStamp at={loadedAt} onRefresh={reload} busy={loading && loadedAt !== null} />}
      />

      <div className="ui-toolbar">
        <Tabs
          label="Evidence lists"
          value={tab}
          onChange={(next) => { setTab(next); setOpenId(null) }}
          items={[
            { key: 'PENDING', label: 'Awaiting review', count: loadedAt ? lists.PENDING.length : null },
            { key: 'VERIFIED', label: 'Verified', count: loadedAt ? lists.VERIFIED.length : null },
            { key: 'REJECTED', label: 'Rejected', count: loadedAt ? lists.REJECTED.length : null },
          ]}
        />
        <div className="ui-filters">
          <input type="search" aria-label="Search students" placeholder="Search student name or zID" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>

      <InfoDisclosure summary="How induction review works">
        <ul>
          <li>Students cannot request bookings until their induction for that resource is verified.</li>
          <li>Verification lasts a fixed period (about one term). After that the student uploads it again.</li>
          <li>Rejecting evidence also rejects that student's undecided booking requests for the resources it covers.</li>
          <li>Admins cannot review their own evidence.</li>
        </ul>
      </InfoDisclosure>

      {error && <p className="bk-error" role="alert">{error}</p>}
      {loading && loadedAt === null && <p role="status">Loading applications…</p>}

      {loadedAt !== null && rows.length === 0 && (
        <EmptyState title={tab === 'PENDING' ? "You're all caught up" : 'Nothing here yet'}>
          {search ? 'No evidence matches this search.' : tab === 'PENDING' ? 'There is no evidence waiting for review.' : `No ${tab.toLowerCase()} evidence.`}
        </EmptyState>
      )}

      {rows.length > 0 && (
        <div className="ui-table-wrap">
          <table className="ui-table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Training</th>
                <th className="ui-hide-sm">Title</th>
                <th>{tab === 'PENDING' ? 'Submitted' : 'Reviewed'}</th>
                {tab !== 'PENDING' && <th className="ui-hide-sm">{tab === 'VERIFIED' ? 'Valid until' : 'Reason'}</th>}
                <th><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((q) => (
                <tr key={q.id} className={`is-clickable${openId === q.id ? ' is-selected' : ''}`} onClick={() => setOpenId(q.id)}>
                  <td>
                    <span className="ui-primary-text">{who(q)}</span>
                    <span className="ui-sub-text">{q.student?.zid}{own(q) ? ' · you' : ''}</span>
                  </td>
                  <td>{requirementName(q)}</td>
                  <td className="ui-hide-sm">{q.title}</td>
                  <td>{fmtRelative(tab === 'PENDING' ? q.submitted_at : q.reviewed_at ?? q.submitted_at, now)}</td>
                  {tab !== 'PENDING' && (
                    <td className="ui-hide-sm">
                      {tab === 'VERIFIED'
                        ? q.effective_status === 'EXPIRED' ? <span className="ui-pill is-red">Expired</span> : q.valid_until ? fmtDateTime(q.valid_until) : '—'
                        : q.rejection_reason ?? '—'}
                    </td>
                  )}
                  <td>
                    <div className="ui-actions">
                      <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={(e) => { e.stopPropagation(); setOpenId(q.id) }}>View</button>
                      {actions(q)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {open && (
        <Drawer
          title={who(open)}
          subtitle={`${open.student?.zid ?? ''}${open.student?.university_email ? ` · ${open.student.university_email}` : ''}`}
          onClose={() => setOpenId(null)}
          footer={actions(open, '')}
        >
          <section>
            <h3>Submission</h3>
            <Facts items={[
              { label: 'Training', value: requirementName(open) },
              { label: 'Title', value: open.title },
              { label: 'Submitted', value: fmtDateTime(open.submitted_at) },
              { label: 'Notes', value: open.notes || '—' },
              ...(open.status === 'VERIFIED' ? [{ label: 'Valid until', value: open.valid_until ? fmtDateTime(open.valid_until) : '—' }] : []),
              ...(open.status === 'REJECTED' ? [{ label: 'Reason', value: open.rejection_reason ?? '—' }] : []),
            ]} />
          </section>
          <section>
            <h3>Evidence</h3>
            <EvidencePreview submissionId={open.id} fileName={`${open.student?.zid ?? 'evidence'}-${open.title}`} />
          </section>
        </Drawer>
      )}
    </>
  )
}
