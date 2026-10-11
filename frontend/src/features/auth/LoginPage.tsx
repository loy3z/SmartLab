import { useEffect, useState, type FormEvent } from 'react'
import { demoLogin, demoRegister, getAuthConfig, setToken } from '../booking/api'
import { errorMessage } from '../booking/format'
import { CalendarIcon, CapIcon, ClockIcon } from '../booking/icons'
import type { AuthConfig } from '../booking/types'
import './auth.css'

export function LoginPage({ notice = '' }: { notice?: string }) {
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
      setToken(result.access_token)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div className="auth-page">
      <a className="auth-skip-link" href="#/login" onClick={(event) => {
        event.preventDefault()
        document.getElementById('auth-title')?.focus()
      }}>Skip to sign in</a>
      <header className="auth-masthead">
        <div className="auth-container auth-masthead-inner">
          <a className="auth-university-logo" href="https://www.unsw.edu.au/" target="_blank" rel="noreferrer">
            <img src="/images/unsw-logo.png" alt="UNSW Sydney — university website (opens in a new tab)" width="330" height="140" />
          </a>
          <nav className="auth-university-links" aria-label="University links">
            <a href="https://www.unsw.edu.au/" target="_blank" rel="noreferrer">UNSW home <span aria-hidden="true">↗</span><span className="auth-visually-hidden"> (opens in a new tab)</span></a>
            <a href="https://www.unsw.edu.au/student" target="_blank" rel="noreferrer">Current students <span aria-hidden="true">↗</span><span className="auth-visually-hidden"> (opens in a new tab)</span></a>
          </nav>
        </div>
      </header>
      <div className="auth-service-bar">
        <div className="auth-container auth-service-inner">
          <span className="auth-service-name">SmartLab<span>Lab & room booking</span></span>
          <span className="auth-service-tag">Student project prototype</span>
        </div>
      </div>
      <main className="auth-container auth-main">
        <div className="auth-breadcrumb" aria-label="Page location"><span>UNSW Sydney</span><span aria-hidden="true">/</span><span>SmartLab</span><span aria-hidden="true">/</span><strong>{register ? 'Create account' : 'Sign in'}</strong></div>
        <div className="auth-content-grid">
          <section className="auth-introduction" aria-labelledby="auth-introduction-title">
            <p className="auth-eyebrow">SPACES TO LEARN. TO EXPLORE. TO CREATE.</p>
            <h1 id="auth-introduction-title">Lab and room<br /> booking.</h1>
            <div className="auth-title-rule" aria-hidden="true" />
            <p className="auth-lead">Find the right space for your next idea.</p>
            <p className="auth-intro-description">Discover shared labs and specialist equipment, check your induction and manage your bookings in one place.</p>
            <figure className="auth-campus">
              <img src="/images/unsw-campus.jpg" alt="Aerial view of UNSW's Kensington campus" width="700" height="366" />
              <figcaption><span aria-hidden="true">●</span> Kensington campus · UNSW Sydney</figcaption>
            </figure>
            <div className="auth-benefits" aria-label="SmartLab services">
              <div><CalendarIcon size={22} /><span>Book a space<small>Labs, rooms & equipment</small></span></div>
              <div><CapIcon size={23} /><span>Check your access<small>Induction & training</small></span></div>
              <div><ClockIcon size={22} /><span>Stay up to date<small>Requests & approvals</small></span></div>
            </div>
          </section>
          <section className="auth-form-side" aria-labelledby="auth-title">
            <div className="auth-form-wrap">
          <p className="auth-form-eyebrow">SMARTLAB ACCESS</p>
          <h2 id="auth-title" tabIndex={-1}>{register ? 'Create an account' : 'Sign in'}</h2>
          <p className="auth-description">{register ? 'Create a student account to get started.' : 'Access your bookings and training records.'}</p>
          {notice && <p className="auth-notice" role="status">{notice}</p>}
          {!config && !configError && <p className="auth-status" role="status">Checking sign-in options…</p>}
          {configError && <div className="auth-error" role="alert"><p>{configError}</p><button className="auth-text-button" onClick={() => { setConfigError(''); setAttempt((n) => n + 1) }}>Try again</button></div>}
          {config && !config.demo_auth_enabled && <div className="auth-notice"><h3>University sign-in is not available yet</h3><p>The university login connection has not been enabled. Please contact your project administrator for access.</p><button className="auth-text-button" onClick={() => { setConfig(null); setAttempt((n) => n + 1) }}>Check again</button></div>}
          {config?.demo_auth_enabled && <>
            <div className="auth-demo-notice"><span>Demo sign-in</span><p>Use a demo zID below. University SSO is not connected; no password is required.</p></div>
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
            {!register && <details className="auth-demo-accounts"><summary>Demo accounts for testing</summary><p>Use an existing account to explore each portal.</p><ul><li><code>z1000001</code> — Student with induction</li><li><code>z1000002</code> — Student awaiting induction</li><li><code>z9000001</code> — Administrator</li><li><code>z9000002</code> — Manager</li></ul></details>}
          </>}
            </div>
            <aside className="auth-support" aria-label="Sign-in help">
              <h3>Need help signing in?</h3>
              <p>For SmartLab account or access enquiries, contact your laboratory administrator.</p>
              <a href="https://www.unsw.edu.au/student/managing-your-studies/resources/logins" target="_blank" rel="noreferrer">Looking for other UNSW services? <span aria-hidden="true">↗</span><span className="auth-visually-hidden"> (opens in a new tab)</span></a>
            </aside>
          </section>
        </div>
      </main>
      <footer className="auth-footer">
        <div className="auth-container auth-footer-inner"><p><strong>UNSW Sydney</strong><span>SmartLab · Lab and room booking</span></p><p className="auth-footer-note">Student project prototype</p></div>
      </footer>
    </div>
  )
}
