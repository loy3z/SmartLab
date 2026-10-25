// Sprint 3: booking freeze notice and unfreeze request on My Bookings.
import { useCallback, useEffect, useState } from 'react'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { listMyUnfreezeRequests, requestUnfreeze } from './api'
import { frozenUntilText } from './attendance'
import { errorMessage } from './format'
import type { UnfreezeRequest } from './types'

/** Shown while the signed-in person's booking is frozen after missed check-ins, with the unfreeze request form. */
export function FreezeNotice() {
  const { user } = useAuth()
  const feedback = useFeedback()
  const [requests, setRequests] = useState<UnfreezeRequest[]>([])
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const frozen = Boolean(user?.booking_frozen && user.frozen_until)

  const load = useCallback(async () => {
    if (!frozen) return
    try { setRequests((await listMyUnfreezeRequests()).results) } catch { setRequests([]) }
  }, [frozen])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  if (!frozen || !user?.frozen_until) return null
  const pending = requests.find((item) => item.status === 'PENDING')
  const latest = requests[0]

  async function send() {
    setBusy(true)
    try {
      await requestUnfreeze(reason.trim())
      setReason('')
      feedback.success('Staff will review your request.', 'Request sent')
      await load()
    } catch (e) {
      feedback.error(errorMessage(e), 'Request not sent')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="ui-callout is-error bk-freeze" role="status" aria-label="Booking frozen">
      <div>
        <strong>Booking frozen until {frozenUntilText(user.frozen_until)}</strong>
        <span>You missed too many check-ins, so your later bookings were cancelled and you cannot book until then.</span>
        {pending ? (
          <span>Your unfreeze request is waiting for staff.</span>
        ) : (
          <>
            {latest?.status === 'REJECTED' && <span>Your last request was rejected: {latest.decision_reason}</span>}
            <label className="bk-freeze-form">
              Ask staff to unfreeze you
              <textarea rows={2} maxLength={1000} value={reason} placeholder="Explain what happened"
                onChange={(e) => setReason(e.target.value)} />
            </label>
            <button type="button" className="ui-btn ui-btn-primary ui-btn-sm" disabled={busy || !reason.trim()} onClick={() => void send()}>
              {busy ? 'Sending…' : 'Send request'}
            </button>
          </>
        )}
      </div>
    </section>
  )
}
