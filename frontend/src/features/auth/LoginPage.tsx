import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router'
import { demoLogin, demoRegister, getAuthConfig, setToken } from '../booking/api'
import { errorMessage } from '../booking/format'
import type { AuthConfig } from '../booking/types'
import { AuthShell } from './AuthShell'

export function LoginPage({ notice = '' }: { notice?: string }) {
  const location = useLocation()
  const mounted = useRef(false)
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [configError, setConfigError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [register, setRegister] = useState(false)
  const [zid, setZid] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !config?.demo_auth_enabled || (register && !config.demo_registration_enabled)) return
    setBusy(true)
    setError('')
    try {
      const result = register
        ? await demoRegister({ zid: zid.trim().toLowerCase(), display_name: name.trim(), university_email: email.trim() })
        : await demoLogin(zid.trim().toLowerCase())
      if (mounted.current) setToken(result.access_token)
    } catch (err) {
      if (mounted.current) {
        setError(errorMessage(err))
        setBusy(false)
      }
    }
  }

  return (
    <AuthShell crumb={register ? 'Create account' : 'Sign in'}>
          <p className="auth-form-eyebrow">SMARTLAB ACCESS</p>
          <h2 id="auth-title" tabIndex={-1}>{register ? 'Create an account' : 'Sign in'}</h2>
          <p className="auth-description">{register ? 'Create a student account to get started.' : 'Access your bookings and training records.'}</p>
          {notice && <p className="auth-notice" role="status">{notice}</p>}
          {!config && !configError && <p className="auth-status" role="status">Checking sign-in options…</p>}
          {configError && <div className="auth-error" role="alert"><p>{configError}</p><button className="auth-text-button" onClick={() => { setConfigError(''); setAttempt((n) => n + 1) }}>Try again</button></div>}
          {config && !config.demo_auth_enabled && <div className="auth-notice"><h3>University sign-in is not available yet</h3><p>The university login connection has not been enabled. Please contact your project administrator for access.</p><button className="auth-text-button" onClick={() => { setConfig(null); setAttempt((n) => n + 1) }}>Check again</button></div>}
          {config?.demo_auth_enabled && <>
            <div className="auth-demo-notice"><span>Simulated university sign-in</span><p>This is a project demonstration. University SSO is not connected. Use demo accounts only; no university password is required.</p></div>
            <Link className="auth-submit auth-sso-entry" to="/login/mock-sso" state={location.state} aria-disabled={busy || undefined} onClick={(event) => { if (busy) event.preventDefault() }}>University sign-in (Demo)<span aria-hidden="true">→</span></Link>
            <p className="auth-sso-caption">For students. Enter your demo zID or university email on the next screen.</p>
            <p className="auth-staff-entry">Admin or Manager? <Link to="/staff/login" state={location.state}>Staff sign-in<span aria-hidden="true"> →</span></Link></p>
            <details className="auth-demo-accounts auth-alternative-login">
              <summary>Other demo sign-in options</summary>
            <form onSubmit={submit} className="auth-form">
              <fieldset disabled={busy}>
                <label htmlFor="auth-zid">University zID</label>
                <input id="auth-zid" name="username" autoComplete="username" placeholder="e.g. z1000001" value={zid} onChange={(event) => setZid(event.target.value)} pattern="[zZ][0-9]{7}" title="Enter z followed by 7 digits" maxLength={8} required aria-describedby="auth-zid-hint" />
                <small id="auth-zid-hint">Your zID starts with z, followed by 7 digits.</small>
                {register && <>
                  <label htmlFor="auth-name">Full name</label>
                  <input id="auth-name" name="name" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={120} />
                  <label htmlFor="auth-email">University email</label>
                  <input id="auth-email" name="email" type="email" autoComplete="email" placeholder="Your university email address" value={email} onChange={(event) => setEmail(event.target.value)} required maxLength={254} />
                </>}
                {error && <p className="auth-error" role="alert">{error}</p>}
                <button className="auth-submit" type="submit">{busy ? 'Signing you in…' : register ? 'Create student account' : 'Sign in'}<span aria-hidden="true">→</span></button>
              </fieldset>
            </form>
            {config.demo_registration_enabled && <p className="auth-switch">{register ? 'Already have an account?' : 'New to the prototype?'} <button className="auth-text-button" disabled={busy} onClick={() => { setRegister(!register); setError('') }}>{register ? 'Sign in' : 'Create student account'}</button></p>}
            </details>
          </>}
    </AuthShell>
  )
}
