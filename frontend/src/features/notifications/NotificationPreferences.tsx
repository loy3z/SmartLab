// Sprint 3 (1.19.0): dedicated settings with separate website/email channels.
import { useEffect, useState } from 'react'
import { useFeedback } from '../../ui/feedback-context'
import { getNotificationPreferences, saveNotificationPreferences } from '../booking/api'
import { errorMessage } from '../booking/format'
import type { NotificationPreference } from '../booking/types'

const CATEGORIES: Record<string, { label: string; description: string }> = {
  bookings: { label: 'Booking updates', description: 'Requests received, approved, rejected, moved, cancelled, waitlisted and expired; weekly series.' },
  reminders: { label: 'Reminders', description: 'Upcoming bookings and induction expiry reminders.' },
  induction: { label: 'Induction and training', description: 'Evidence received, verified or rejected.' },
  account: { label: 'Account and booking freeze', description: 'Missed check-ins, booking freezes, unfreeze decisions and restored access.' },
  resources: { label: 'Room and equipment status', description: 'Maintenance, closures and reopening affecting your bookings.' },
}
export function NotificationPreferences() {
  const feedback = useFeedback()
  const [items, setItems] = useState<NotificationPreference[]>([])
  const [emailAvailable, setEmailAvailable] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    getNotificationPreferences().then(data => {
      if (active) { setItems(data.results); setEmailAvailable(data.email_available); setError('') }
    }).catch(reason => { if (active) setError(errorMessage(reason)) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])
  async function toggle(category: string, channel: 'in_app' | 'email', enabled: boolean) {
    setBusy(true); setError('')
    try {
      const data = await saveNotificationPreferences({ [category]: { [channel]: enabled } })
      setItems(data.results); setEmailAvailable(data.email_available)
      feedback.success('Notification settings saved')
    } catch (reason) { setError(errorMessage(reason)) }
    finally { setBusy(false) }
  }
  return <section className="notification-settings">
    <h1>Notifications</h1>
    <div className="app-card">
      <p>Choose how you receive each type of update. Changes are saved immediately.</p>
      {!loading && !emailAvailable && <p className="notification-email-note">Email is not switched on for this site.</p>}
      {loading && <p role="status">Loading notification settings…</p>}
      {error && <p className="bk-error" role="alert">{error} <button className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setAttempt(value => value + 1)}>Retry settings</button></p>}
      {items.length > 0 && <div className="notification-matrix">
        <div className="notification-matrix-head" aria-hidden="true"><span>Category</span><span>In the bell</span><span>By email</span></div>
        {items.map(item => <div key={item.category} className="notification-matrix-row">
          <div><h2>{CATEGORIES[item.category]?.label ?? item.category}</h2><p>{CATEGORIES[item.category]?.description}</p></div>
          {/* Review Q1 (2026-10-27): with email off the email column shows unchecked; the saved choice is kept and shows again once email is on. */}
          {(['in_app', 'email'] as const).map(channel => <label key={channel}>
            <span>{channel === 'in_app' ? 'In the bell' : 'By email'}</span>
            <input type="checkbox" checked={item[channel] && (channel === 'in_app' || emailAvailable)} disabled={busy || (channel === 'email' && !emailAvailable)}
              aria-label={`${CATEGORIES[item.category]?.label ?? item.category}: ${channel === 'in_app' ? 'In the bell' : 'By email'}`}
              onChange={event => void toggle(item.category, channel, event.target.checked)} />
          </label>)}
        </div>)}
      </div>}
    </div>
  </section>
}
