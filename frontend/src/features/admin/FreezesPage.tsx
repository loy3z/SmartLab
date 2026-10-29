// Sprint 3: Booking freezes page (Admin/Manager): unfreeze requests and frozen people.
import { useCallback, useEffect, useState } from 'react'
import { EmptyState, PageHeader, RefreshStamp } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { listFrozenUsers, listUnfreezeRequests, reviewUnfreeze, unfreezeUser } from '../../api/index.ts'
import { frozenUntilText } from '../booking/attendance'
import { errorMessage, fmtDateTime } from '../booking/format'
import type { FrozenUser, UnfreezeRequest } from '../../api/types/index.ts'

/**
 * Admin/Manager: people whose booking is frozen after missed check-ins, and their unfreeze requests.
 * Freezing only stops booking; frozen staff keep their reviewing rights. You cannot decide your own request.
 */
export function FreezesPage() {
  const feedback = useFeedback()
  const { user } = useAuth()
  const [requests, setRequests] = useState<UnfreezeRequest[]>([])
  const [frozen, setFrozen] = useState<FrozenUser[]>([])
  const [loadedAt, setLoadedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [pending, people] = await Promise.all([listUnfreezeRequests('PENDING'), listFrozenUsers()])
      setRequests(pending.results)
      setFrozen(people.results)
      setLoadedAt(Date.now())
      setError('')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  async function decide(item: UnfreezeRequest, decision: 'APPROVED' | 'REJECTED') {
    const name = item.person ? `${item.person.display_name} (${item.person.zid})` : 'this person'
    const answer = await feedback.confirm({
      title: decision === 'APPROVED' ? `Unfreeze ${name}?` : `Reject the request from ${name}?`,
      details: [{ label: 'Their reason', value: item.reason }],
      message: decision === 'APPROVED' ? 'They can book again at once. Cancelled bookings are not restored.' : undefined,
      confirmLabel: decision === 'APPROVED' ? 'Unfreeze' : 'Reject request',
      danger: decision === 'REJECTED',
      reason: decision === 'REJECTED' ? { label: 'Reason (shown to them)', required: true, maxLength: 2000 } : undefined,
    })
    if (!answer.confirmed) return
    setBusy(item.id)
    try {
      await reviewUnfreeze(item.id, decision, answer.reason)
      feedback.success(name, decision === 'APPROVED' ? 'Unfrozen' : 'Request rejected')
    } catch (e) {
      feedback.error(errorMessage(e), 'Not saved')
    } finally {
      setBusy(null)
      await load()
    }
  }

  async function lift(person: FrozenUser) {
    const answer = await feedback.confirm({
      title: `Unfreeze ${person.display_name} (${person.zid})?`,
      message: 'They can book again at once. Cancelled bookings are not restored.',
      confirmLabel: 'Unfreeze',
      reason: { label: 'Note', required: false, maxLength: 1000 },
    })
    if (!answer.confirmed) return
    setBusy(person.id)
    try {
      await unfreezeUser(person.id, answer.reason)
      feedback.success(`${person.display_name} (${person.zid})`, 'Unfrozen')
    } catch (e) {
      feedback.error(errorMessage(e), 'Not unfrozen')
    } finally {
      setBusy(null)
      await load()
    }
  }

  return (
    <>
      <PageHeader
        title="Booking freezes"
        description="People who missed too many check-ins cannot book until their freeze ends or you lift it."
        actions={<RefreshStamp at={loadedAt} onRefresh={() => void load()} busy={loading && loadedAt !== null} />}
      />
      {error && <p className="bk-error" role="alert">{error}</p>}
      {loading && loadedAt === null && <p role="status">Loading…</p>}

      <h2 className="bk-h2">Unfreeze requests <small>{requests.length}</small></h2>
      {requests.length === 0 && loadedAt !== null ? (
        <EmptyState title="No requests waiting">People who are frozen can ask to be unfrozen from their bookings page.</EmptyState>
      ) : (
        <div className="ui-table-wrap">
          <table className="ui-table" aria-label="Unfreeze requests">
            <thead><tr><th>Person</th><th>Frozen until</th><th>Reason</th><th>Sent</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {requests.map((item) => (
                <tr key={item.id}>
                  <td><span className="ui-primary-text">{item.person?.display_name}</span><span className="ui-sub-text">{item.person?.zid} · {item.person?.role}</span></td>
                  <td>{item.person?.frozen_until ? frozenUntilText(item.person.frozen_until) : '—'}</td>
                  <td>{item.reason}</td>
                  <td>{fmtDateTime(item.created_at)}</td>
                  <td>
                    {item.principal_id === user?.id ? <span className="ui-sub-text">Your own request: another staff member decides</span> : (
                      <div className="ui-actions">
                        <button className="ui-btn ui-btn-sm" disabled={busy !== null} onClick={() => void decide(item, 'APPROVED')}>Unfreeze</button>
                        <button className="ui-btn ui-btn-reject ui-btn-sm" disabled={busy !== null} onClick={() => void decide(item, 'REJECTED')}>Reject</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="bk-h2">Frozen now <small>{frozen.length}</small></h2>
      {frozen.length === 0 && loadedAt !== null ? (
        <EmptyState title="Nobody is frozen" />
      ) : (
        <div className="ui-table-wrap">
          <table className="ui-table" aria-label="Frozen people">
            <thead><tr><th>Person</th><th>Frozen until</th><th>Request</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {frozen.map((person) => (
                <tr key={person.id}>
                  <td><span className="ui-primary-text">{person.display_name}</span><span className="ui-sub-text">{person.zid} · {person.role}</span></td>
                  <td>{person.frozen_until ? frozenUntilText(person.frozen_until) : '—'}</td>
                  <td>{person.pending_request ? 'Waiting for review' : '—'}</td>
                  <td>
                    {person.id !== user?.id && (
                      <button className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy !== null} onClick={() => void lift(person)}>Unfreeze</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
