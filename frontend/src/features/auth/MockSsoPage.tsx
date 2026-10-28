import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router'
import { demoLogin, demoRegister, getAuthConfig, setToken } from '../../api/index.ts'
import { errorMessage } from '../booking/format'
import type { AuthConfig } from '../../api/types/index.ts'
import './mock-sso.css'

// University sign-in is for students. Admins and Managers use the staff sign-in page.
const demoAccounts = [
  ['z1000001', 'Student with induction'],
  ['z1000002', 'Student without induction'],
] as const

export function MockSsoPage({ notice = '' }: { notice?: string }) {
  const location = useLocation()
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [configError, setConfigError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [account, setAccount] = useState('')
  // Sprint 3 (2026-10-25, Loy): new demo students sign up here, since the sign-in hub no longer has a direct form.
  const [creating, setCreating] = useState(false)
  const [newZid, setNewZid] = useState('')
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ReactNode>('')
  const mounted = useRef(false)
  const pending = useRef(false)
  const requestId = useRef(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const optionsRef = useRef<HTMLDetailsElement>(null)

  useEffect(() => {
    mounted.current = true
    document.getElementById('mock-sso-title')?.focus({ preventScroll: true })
    return () => {
      mounted.current = false
      requestId.current += 1
    }
  }, [])

  useEffect(() => {
    let active = true
    getAuthConfig().then((value) => { if (active) setConfig(value) })
      .catch((err) => { if (active) setConfigError(errorMessage(err)) })
    return () => { active = false }
  }, [attempt])

  function retryConfig() {
    setConfig(null)
    setConfigError('')
    setAttempt((value) => value + 1)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current || !config?.demo_auth_enabled) return
    // Email is only a demo alias for the zID; this does not verify mailbox ownership.
    const match = /^(z[0-9]{7})(?:@ad\.unsw\.edu\.au)?$/i.exec(account.trim())
    if (!match) {
      setError('Enter a demo zID such as z1000001, or z1000001@ad.unsw.edu.au.')
      inputRef.current?.focus()
      return
    }
    pending.current = true
    const currentRequest = ++requestId.current
    setBusy(true)
    setError('')
    try {
      const result = await demoLogin(match[1].toLowerCase())
      if (!mounted.current || currentRequest !== requestId.current) return
      // AuthProvider verifies the backend token and loads the authoritative role.
      setToken(result.access_token)
    } catch (err) {
      if (!mounted.current || currentRequest !== requestId.current) return
      pending.current = false
      setBusy(false)
      // Sprint 3 (2026-10-28 feedback L1): staff accounts get a direct link instead of plain text.
      setError((err as { code?: string })?.code === 'USE_STAFF_SIGN_IN'
        ? <>Admins and Managers sign in on the <Link to="/staff/login" state={location.state}>Staff sign-in page</Link>.</>
        : errorMessage(err))
    }
  }

  /** Sprint 3 (2026-10-25): create a demo student account (auth/demo-register/) and sign in with it. */
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current || !config?.demo_registration_enabled) return
    const zid = newZid.trim().toLowerCase()
    if (!/^z[0-9]{7}$/.test(zid)) {
      setError('Enter a zID: z followed by 7 digits, such as z5555555.')
      return
    }
    if (!newName.trim() || !newEmail.trim()) {
      setError('Enter your full name and university email.')
      return
    }
    pending.current = true
    const currentRequest = ++requestId.current
    setBusy(true)
    setError('')
    try {
      const result = await demoRegister({ zid, display_name: newName.trim(), university_email: newEmail.trim() })
      if (!mounted.current || currentRequest !== requestId.current) return
      setToken(result.access_token)
    } catch (err) {
      if (!mounted.current || currentRequest !== requestId.current) return
      pending.current = false
      setBusy(false)
      setError(errorMessage(err))
    }
  }

  function switchMode(next: boolean) {
    setCreating(next)
    setError('')
  }

  function showAccounts() {
    if (!optionsRef.current) return
    optionsRef.current.open = true
    optionsRef.current.querySelector('summary')?.focus()
    optionsRef.current.scrollIntoView({ block: 'nearest' })
  }

  return (
    <div className="mock-sso-page">
      <main className="mock-sso-content" aria-labelledby="mock-sso-title">
        <section className="mock-sso-card">
          <div className="mock-sso-main">
            <div className="mock-sso-brand">
              <img src="/images/unsw-logo.png" alt="UNSW Sydney" width="330" height="140" />
              <span className="mock-sso-tag">Mock SSO</span>
            </div>
            <h1 id="mock-sso-title" tabIndex={-1}>{creating ? 'Create account' : 'Sign in'}</h1>
            {notice && <p className="mock-sso-notice" role="status">{notice}</p>}
            {!config && !configError && <p className="mock-sso-status" role="status">Checking sign-in options…</p>}
            {configError && <div className="mock-sso-error" role="alert"><p>{configError}</p><button className="mock-sso-text-button" onClick={retryConfig}>Try again</button></div>}
            {config && !config.demo_auth_enabled && <div className="mock-sso-notice"><h2>University sign-in is not available yet</h2><p>Demo sign-in is disabled. Contact your project administrator for access.</p><button className="mock-sso-text-button" onClick={retryConfig}>Check again</button></div>}
            {config?.demo_auth_enabled && !creating && <form onSubmit={submit} noValidate aria-busy={busy}>
              <fieldset disabled={busy}>
                <label className="mock-sso-visually-hidden" htmlFor="mock-sso-account">Demo zID or university email</label>
                <input
                  ref={inputRef}
                  id="mock-sso-account"
                  name="username"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  placeholder="zID@ad.unsw.edu.au"
                  value={account}
                  onChange={(event) => { setAccount(event.target.value); setError('') }}
                  maxLength={64}
                  required
                  aria-invalid={error ? true : undefined}
                  aria-describedby={`mock-sso-hint${error ? ' mock-sso-error' : ''}`}
                />
                <p id="mock-sso-hint" className="mock-sso-hint">Enter a demo zID or its @ad.unsw.edu.au email address.</p>
                {error && <p id="mock-sso-error" className="mock-sso-error" role="alert">{error}</p>}
                {config.demo_registration_enabled && <p className="mock-sso-create">No demo account? <button className="mock-sso-text-button" type="button" onClick={() => switchMode(true)}>Create one</button></p>}
                <button className="mock-sso-text-button mock-sso-help-link" type="button" onClick={showAccounts}>Can't access your demo account?</button>
                <div className="mock-sso-actions"><button className="mock-sso-next" type="submit">{busy ? 'Signing in…' : 'Next'}</button></div>
              </fieldset>
              {busy && <p className="mock-sso-visually-hidden" role="status">Signing in to SmartLab…</p>}
            </form>}
            {/* Sprint 3 (2026-10-25, Loy): demo sign-up for a new student zID. */}
            {config?.demo_auth_enabled && config.demo_registration_enabled && creating && <form onSubmit={create} noValidate aria-busy={busy}>
              <fieldset disabled={busy}>
                <p className="mock-sso-hint mock-sso-create-intro">Demo only: creates a student account. No university password is used.</p>
                <label className="mock-sso-visually-hidden" htmlFor="mock-sso-new-zid">zID</label>
                <input id="mock-sso-new-zid" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} placeholder="zID, e.g. z5555555"
                  value={newZid} onChange={(event) => { setNewZid(event.target.value); setError('') }} maxLength={16} required autoFocus
                  aria-invalid={error ? true : undefined} aria-describedby={error ? 'mock-sso-error' : undefined} />
                <label className="mock-sso-visually-hidden" htmlFor="mock-sso-new-name">Full name</label>
                <input id="mock-sso-new-name" name="name" autoComplete="name" placeholder="Full name"
                  value={newName} onChange={(event) => { setNewName(event.target.value); setError('') }} maxLength={120} required />
                <label className="mock-sso-visually-hidden" htmlFor="mock-sso-new-email">University email</label>
                <input id="mock-sso-new-email" name="email" type="email" autoComplete="email" placeholder="University email"
                  value={newEmail} onChange={(event) => { setNewEmail(event.target.value); setError('') }} maxLength={254} required />
                {error && <p id="mock-sso-error" className="mock-sso-error" role="alert">{error}</p>}
                <div className="mock-sso-actions">
                  <button className="mock-sso-back" type="button" onClick={() => switchMode(false)}>Back</button>
                  <button className="mock-sso-next" type="submit">{busy ? 'Creating…' : 'Create'}</button>
                </div>
              </fieldset>
              {busy && <p className="mock-sso-visually-hidden" role="status">Creating your demo account…</p>}
            </form>}
          </div>
          <aside className="mock-sso-help" aria-label="About this demonstration">
            <h2>SmartLab demonstration</h2>
            <p>University SSO is not connected. Use an existing demo account; no university password is required.</p>
            <p>Need a test account? Open <strong>Sign-in options</strong> below to see the demo zIDs.</p>
            <Link to="/login" state={location.state} replace>Back to SmartLab</Link>
          </aside>
        </section>
        {config?.demo_auth_enabled && <details className="mock-sso-options" ref={optionsRef}>
          <summary>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="5" /><path d="m11.5 11.5 3 3H18v3h3V21h-4l-6-6M6 6h.01" /></svg>
            <span>Sign-in options</span>
            <span className="mock-sso-chevron" aria-hidden="true">⌄</span>
          </summary>
          <div className="mock-sso-options-content">
            <p>Enter one of these demo zIDs above, then select <strong>Next</strong>.</p>
            <dl>{demoAccounts.map(([zid, name]) => <div key={zid}><dt>{name}</dt><dd><code>{zid}</code></dd></div>)}</dl>
            <p>Student training descriptions refer to the initial demo data. Admins and Managers sign in on the <Link to="/staff/login">staff sign-in page</Link>.</p>
          </div>
        </details>}
      </main>
      <footer className="mock-sso-footer"><span>SmartLab · Student project prototype</span><span>Simulated university sign-in</span></footer>
    </div>
  )
}
