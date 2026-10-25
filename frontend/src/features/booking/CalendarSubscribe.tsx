// Sprint 3: calendar subscription link on My Bookings.
import { useState } from 'react'
import { useFeedback } from '../../ui/feedback-context'
import { getCalendarLink, resetCalendarLink } from './api'
import { calendarUrl } from './attendance'
import { errorMessage } from './format'

// Sprint 3 (1.16.0): steps for each calendar app (menu names can differ slightly between versions).
const CALENDAR_APPS = {
  outlook: { name: 'Outlook', steps: ['Open Calendar and choose Add calendar.', 'Choose Subscribe from web and paste the link.', 'Give it a name such as SmartLab and choose Import.'] },
  google: { name: 'Google Calendar', steps: ['On a computer, open Google Calendar.', 'Next to Other calendars choose + and then From URL.', 'Paste the link and choose Add calendar. It then also shows on your phone.'] },
  apple: { name: 'Apple Calendar', steps: ['Mac: in Calendar choose File → New Calendar Subscription, paste the link and choose Subscribe.', 'iPhone or iPad: Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar, then paste the link.', 'Set Auto-refresh to the shortest time offered.'] },
} as const
type CalendarApp = keyof typeof CALENDAR_APPS

/** "Subscribe in calendar": a private address Outlook, Google or Apple Calendar reads by itself. */
export function CalendarSubscribe() {
  const feedback = useFeedback()
  const [url, setUrl] = useState('')
  const [app, setApp] = useState<CalendarApp>('outlook')
  const [busy, setBusy] = useState(false)

  async function show() {
    setBusy(true)
    try {
      setUrl(calendarUrl((await getCalendarLink()).path, window.location.origin))
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not get your calendar link')
    } finally {
      setBusy(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      feedback.success(`Now follow the ${CALENDAR_APPS[app].name} steps below.`, 'Link copied')
    } catch {
      feedback.info('Select the address and copy it.', 'Copy the link')
    }
  }

  async function renew() {
    const ok = await feedback.confirm({
      title: 'Make a new link?',
      message: 'The old link stops working at once. Remove the old SmartLab calendar from your calendar app, then subscribe again with the new link.',
      confirmLabel: 'Make a new link',
      danger: true,
    })
    if (!ok.confirmed) return
    setBusy(true)
    try {
      setUrl(calendarUrl((await resetCalendarLink()).path, window.location.origin))
      feedback.success('Subscribe again with the new link.', 'New link made')
    } catch (e) {
      feedback.error(errorMessage(e), 'Could not make a new link')
    } finally {
      setBusy(false)
    }
  }

  // Sprint 3 (compact page top): only a small button until the person asks for the link.
  if (!url) {
    return (
      <div className="bk-calsub-button">
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy} onClick={() => void show()}
          title="Approved bookings appear in Outlook, Google or Apple Calendar by themselves">
          {busy ? 'Loading…' : 'Subscribe in calendar'}
        </button>
      </div>
    )
  }
  return (
    <section className="bk-calsub" aria-label="Calendar subscription">
      <div>
        <strong>Your private calendar link</strong>
        <p className="bk-muted">
          Approved bookings appear in your calendar by themselves. Keep the link private: anyone with it can see your bookings.
        </p>
      </div>
      {/* Sprint 3 (1.16.0): steps for Outlook, Google and Apple, and what to expect after a change. */}
      <div className="bk-calsub-apps" role="tablist" aria-label="Calendar app">
        {(Object.keys(CALENDAR_APPS) as CalendarApp[]).map((key) => (
          <button key={key} type="button" role="tab" aria-selected={app === key} className={`bk-pill ${app === key ? 'is-on' : ''}`} onClick={() => setApp(key)}>
            {CALENDAR_APPS[key].name}
          </button>
        ))}
      </div>
      <ol className="bk-calsub-steps">{CALENDAR_APPS[app].steps.map((step) => <li key={step}>{step}</li>)}</ol>
      <p className="bk-muted bk-calsub-delay">
        Calendar apps check the link every few hours (Google can take up to a day), so a change or cancellation can take a
        while to show there. The status on My Bookings is always the one that counts. The link has to be reachable from the
        internet, so it does not work while the site only runs on your own computer.
      </p>
      <div className="bk-calsub-link">
        <input aria-label="Calendar subscription link" readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="ui-btn ui-btn-primary ui-btn-sm" onClick={() => void copy()}>Copy</button>
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" disabled={busy} onClick={() => void renew()}>Make a new link</button>
        <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setUrl('')}>Hide</button>
      </div>
    </section>
  )
}
