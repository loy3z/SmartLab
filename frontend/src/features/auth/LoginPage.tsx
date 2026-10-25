import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { getAuthConfig } from '../booking/api'
import { errorMessage } from '../booking/format'
import type { AuthConfig } from '../booking/types'
import { AuthShell } from './AuthShell'

/** Sign-in hub: simulated university sign-in (students), staff sign-in and the local test console. */
export function LoginPage({ notice = '' }: { notice?: string }) {
  const location = useLocation()
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [configError, setConfigError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    document.getElementById('auth-title')?.focus({ preventScroll: true })
  }, [])

  useEffect(() => {
    let active = true
    getAuthConfig().then((value) => { if (active) setConfig(value) })
      .catch((err) => { if (active) setConfigError(errorMessage(err)) })
    return () => { active = false }
  }, [attempt])

  return (
    <AuthShell crumb="Sign in">
          {/* Sprint 3 (internal-tool UI, AI-2): no eyebrow above the form title. */}
          <h2 id="auth-title" tabIndex={-1}>Sign in</h2>
          <p className="auth-description">Access your bookings and training records.</p>
          {notice && <p className="auth-notice" role="status">{notice}</p>}
          {!config && !configError && <p className="auth-status" role="status">Checking sign-in options…</p>}
          {configError && <div className="auth-error" role="alert"><p>{configError}</p><button className="auth-text-button" onClick={() => { setConfigError(''); setAttempt((n) => n + 1) }}>Try again</button></div>}
          {config && !config.demo_auth_enabled && <div className="auth-notice"><h3>University sign-in is not available yet</h3><p>The university login connection has not been enabled. Please contact your project administrator for access.</p><button className="auth-text-button" onClick={() => { setConfig(null); setAttempt((n) => n + 1) }}>Check again</button></div>}
          {config?.demo_auth_enabled && <>
            <div className="auth-demo-notice"><span>Simulated university sign-in</span><p>This is a project demonstration. University SSO is not connected. Use demo accounts only; no university password is required.</p></div>
            <Link className="auth-submit auth-sso-entry" to="/login/mock-sso" state={location.state}>University sign-in (Demo)<span aria-hidden="true">→</span></Link>
            <p className="auth-sso-caption">For students. Enter your demo zID or university email on the next screen.</p>
            <p className="auth-staff-entry">Admin or Manager? <Link to="/staff/login" state={location.state}>Staff sign-in<span aria-hidden="true"> →</span></Link></p>
            {config.test_console_enabled && <p className="auth-staff-entry">Local testing? <Link to="/test/login" state={location.state}>Test console →</Link></p>}
          </>}
    </AuthShell>
  )
}
