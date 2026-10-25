import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { getAuthConfig, setToken, testLogin } from '../booking/api'
import { errorMessage } from '../booking/format'
import { AuthShell } from './AuthShell'

export function TestLoginPage() {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [loginId, setLoginId] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    let active = true
    getAuthConfig().then(config => { if (active) setEnabled(Boolean(config.test_console_enabled)) })
      .catch(e => { if (active) setError(errorMessage(e)) })
    return () => { active = false; mounted.current = false }
  }, [])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!enabled || busy) return
    setBusy(true)
    setError('')
    try {
      const result = await testLogin(loginId.trim())
      if (mounted.current) setToken(result.access_token)
    } catch (e) {
      if (mounted.current) {
        setError(errorMessage(e))
        setBusy(false)
      }
    }
  }
  return <AuthShell crumb="Test console">
    {/* Sprint 3 (internal-tool UI, AI-2): no eyebrow above the form title. */}
    <h2 id="auth-title" tabIndex={-1}>Test console</h2>
    <p className="auth-description">Use account 1 without a password. Switch roles and booking rules after signing in.</p>
    {enabled === null && !error && <p role="status">Checking test access…</p>}
    {enabled === false && <p className="auth-notice">The test console is disabled. Start the local backend with test access enabled.</p>}
    {error && <p className="auth-error" role="alert">{error}</p>}
    {enabled && <form className="auth-form" onSubmit={submit}>
      <fieldset disabled={busy}>
        <label htmlFor="test-login-id">Test account ID</label>
        <input id="test-login-id" value={loginId} onChange={e => setLoginId(e.target.value)}
          placeholder="1" pattern="1" required autoComplete="off" />
        <button type="submit" className="auth-submit">{busy ? 'Signing in…' : 'Enter test console'}</button>
      </fieldset>
    </form>}
    <Link to="/login">Back to sign in</Link>
  </AuthShell>
}
