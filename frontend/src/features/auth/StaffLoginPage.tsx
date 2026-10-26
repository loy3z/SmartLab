import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router'
import { getAuthConfig, setToken, staffActivate, staffSignIn } from '../../api/index.ts'
import { errorMessage } from '../booking/format'
import type { AuthConfig } from '../../api/types/index.ts'
import { AuthShell } from './AuthShell'

type Mode = 'sign-in' | 'activate'

/**
 * Staff entry point: Admins and Managers sign in with zID + password (students use university sign-in).
 * A Manager creates the staff account and hands over an invite code; the first visit activates the
 * account by choosing a password. The server decides Admin or Manager from the account itself.
 */
export function StaffLoginPage({ notice = '' }: { notice?: string }) {
  const location = useLocation()
  const mounted = useRef(false)
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [configError, setConfigError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [mode, setMode] = useState<Mode>('sign-in')
  const [zid, setZid] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    mounted.current = true
    document.getElementById('auth-title')?.focus({ preventScroll: true })
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    let active = true
    getAuthConfig().then((value) => { if (active) setConfig(value) })
      .catch((err) => { if (active) setConfigError(errorMessage(err)) })
    return () => { active = false }
  }, [attempt])

  function switchMode(next: Mode) {
    setMode(next)
    setError('')
    setPassword('')
    setConfirm('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const id = zid.trim().toLowerCase()
    if (!/^z\d{7}$/.test(id)) return setError('zID must be z followed by 7 digits, e.g. z9000001.')
    if (mode === 'activate') {
      if (password.length < 8) return setError('Choose a password of at least 8 characters.')
      if (password !== confirm) return setError('The two passwords do not match.')
    }
    setBusy(true)
    setError('')
    try {
      const result = mode === 'sign-in'
        ? await staffSignIn(id, password)
        : await staffActivate({ zid: id, invite_code: code.trim(), password })
      // AuthProvider loads the account and its role; the router then opens the right portal.
      if (mounted.current) setToken(result.access_token)
    } catch (err) {
      if (mounted.current) {
        setError(errorMessage(err))
        setBusy(false)
      }
    }
  }

  const enabled = config?.demo_auth_enabled && config.staff_sign_in_enabled !== false
  const activating = mode === 'activate'
  return (
    <AuthShell crumb="Staff sign-in">
      {/* Sprint 3 (internal-tool UI, AI-2): no eyebrow above the form title. */}
      <h2 id="auth-title" tabIndex={-1}>{activating ? 'Activate your staff account' : 'Staff sign-in'}</h2>
      <p className="auth-description">
        {activating
          ? 'Use the invite code from your Manager and choose a password. You only do this once.'
          : 'For Admins and Managers. Your account decides which pages you see.'}
      </p>
      {notice && <p className="auth-notice" role="status">{notice}</p>}
      {!config && !configError && <p className="auth-status" role="status">Checking sign-in options…</p>}
      {configError && <div className="auth-error" role="alert"><p>{configError}</p><button className="auth-text-button" onClick={() => { setConfigError(''); setAttempt((n) => n + 1) }}>Try again</button></div>}
      {config && !enabled && <div className="auth-notice"><h3>Staff sign-in is not available</h3><p>Contact your project administrator for access.</p></div>}
      {enabled && <>
        <form onSubmit={submit} className="auth-form" noValidate>
          <fieldset disabled={busy}>
            <label htmlFor="staff-zid">Staff zID</label>
            <input id="staff-zid" name="username" autoComplete="username" placeholder="e.g. z9000001" value={zid}
              onChange={(event) => setZid(event.target.value)} maxLength={8} required />
            {activating && <>
              <label htmlFor="staff-code">Invite code</label>
              <input id="staff-code" name="invite-code" autoComplete="one-time-code" placeholder="e.g. K7Q4-9MZD" value={code}
                onChange={(event) => setCode(event.target.value)} maxLength={20} required />
            </>}
            <label htmlFor="staff-password">{activating ? 'New password' : 'Password'}</label>
            <input id="staff-password" name="password" type="password" autoComplete={activating ? 'new-password' : 'current-password'}
              value={password} onChange={(event) => setPassword(event.target.value)} maxLength={128} required />
            {activating && <>
              <small>At least 8 characters.</small>
              <label htmlFor="staff-confirm">Confirm new password</label>
              <input id="staff-confirm" name="confirm-password" type="password" autoComplete="new-password" value={confirm}
                onChange={(event) => setConfirm(event.target.value)} maxLength={128} required />
            </>}
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button className="auth-submit" type="submit">
              {busy ? 'Signing you in…' : activating ? 'Activate and sign in' : 'Sign in'}<span aria-hidden="true">→</span>
            </button>
          </fieldset>
        </form>
        <p className="auth-switch">
          {activating ? 'Already activated?' : 'First time here?'}{' '}
          <button className="auth-text-button" type="button" disabled={busy} onClick={() => switchMode(activating ? 'sign-in' : 'activate')}>
            {activating ? 'Sign in with your password' : 'Activate your account with an invite code'}
          </button>
        </p>
        <p className="auth-switch">Forgot your password? Ask a Manager to reset your access; they will give you a new invite code.</p>
        <div className="auth-demo-notice"><span>Demo staff accounts</span><p>z9000001 (Admin) and z9000002 (Manager), password <code>123</code>.</p></div>
      </>}
      <p className="auth-switch"><Link to="/login" state={location.state}>Student? Use university sign-in</Link></p>
    </AuthShell>
  )
}
