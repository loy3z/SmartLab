// Sprint 3: Admins and Managers change their own password on the Account page (students use university sign-in).
import { useState, type FormEvent } from 'react'
import { useFeedback } from '../../ui/feedback-context'
import { changePassword } from '../../api/index.ts'
import { errorMessage } from '../booking/format'

export function ChangePassword() {
  const feedback = useFeedback()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const problem = next && next.length < 8 ? 'Use at least 8 characters.' : repeat && repeat !== next ? 'The two new passwords differ.' : ''

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy || problem || !current || !next || next !== repeat) return
    setBusy(true)
    setError('')
    try {
      await changePassword(current, next)
      setCurrent(''); setNext(''); setRepeat('')
      feedback.success('Use the new password next time you sign in.', 'Password changed')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="app-card" onSubmit={submit} aria-label="Change password">
      <h2>Change password</h2>
      <label className="ui-field"><span>Current password</span>
        <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label className="ui-field"><span>New password</span>
        <input type="password" autoComplete="new-password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
      </label>
      <label className="ui-field"><span>New password again</span>
        <input type="password" autoComplete="new-password" required value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </label>
      {(problem || error) && <p className={error ? 'bk-error' : 'bk-muted'} role="alert">{error || problem}</p>}
      <button type="submit" className="ui-btn ui-btn-primary" disabled={busy || Boolean(problem) || !current || !next || next !== repeat}>
        {busy ? 'Saving…' : 'Change password'}
      </button>
    </form>
  )
}
