// Sprint 3 (2026-10-25): per-person notification switches on the Account page.
import { useEffect, useState } from 'react'
import { useFeedback } from '../../ui/feedback-context'
import { getNotificationPreferences, saveNotificationPreferences } from '../booking/api'
import { errorMessage } from '../booking/format'
import type { NotificationPreference } from '../booking/types'

const LABELS: Record<string, string> = {
  bookings: 'Booking updates',
  reminders: 'Reminders',
  induction: 'Induction and training',
  account: 'Account and booking freeze',
  resources: 'Room and equipment status',
}

/** Checkboxes for the categories a person can switch off; the urgent-request notice is not listed. */
export function NotificationPreferences() {
  const feedback = useFeedback()
  const [items, setItems] = useState<NotificationPreference[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getNotificationPreferences()
      .then((data) => setItems(data.results))
      .catch((err) => setError(errorMessage(err)))
  }, [])

  async function toggle(category: string, enabled: boolean) {
    setBusy(true)
    setError('')
    try {
      const data = await saveNotificationPreferences({ [category]: enabled })
      setItems(data.results)
      feedback.success(enabled ? 'Turned on' : 'Turned off', LABELS[category] ?? category)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="app-card">
      <h2>Notifications</h2>
      <p>Choose what appears in the bell. Turning a category off stops its website notifications; booking rules do not change.</p>
      {error && <p className="bk-error" role="alert">{error}</p>}
      <ul className="app-pref-list">
        {items.map((item) => (
          <li key={item.category}>
            <label>
              <input type="checkbox" checked={item.enabled} disabled={busy}
                onChange={(event) => void toggle(item.category, event.target.checked)} />
              {LABELS[item.category] ?? item.category}
            </label>
          </li>
        ))}
      </ul>
    </section>
  )
}
