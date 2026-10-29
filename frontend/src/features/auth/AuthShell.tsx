import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router'
import './auth.css'

/** Shared UNSW-style frame for the student and staff sign-in pages. */
export function AuthShell({ crumb, children }: { crumb: string; children: ReactNode }) {
  const location = useLocation()
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
        <div className="auth-breadcrumb" aria-label="Page location"><span>UNSW Sydney</span><span aria-hidden="true">/</span>{/* Sprint 3 (2026-10-28 feedback L4): a way back to the sign-in choices. */}<Link to="/login" state={location.state}>SmartLab</Link><span aria-hidden="true">/</span><strong>{crumb}</strong></div>
        <div className="auth-content-grid">
          {/* Sprint 3 (internal-tool UI, AI-2 / D7): the service name and one plain line; no slogan, eyebrow or feature list. */}
          <section className="auth-introduction" aria-labelledby="auth-introduction-title">
            <h1 id="auth-introduction-title">SmartLab</h1>
            <div className="auth-title-rule" aria-hidden="true" />
            <p className="auth-intro-description">Book lab rooms and equipment at UNSW.</p>
            <figure className="auth-campus">
              <img src="/images/unsw-campus.jpg" alt="Aerial view of UNSW's Kensington campus" width="700" height="366" />
              <figcaption><span aria-hidden="true">●</span> Kensington campus · UNSW Sydney</figcaption>
            </figure>
          </section>
          <section className="auth-form-side" aria-labelledby="auth-title">
            <div className="auth-form-wrap">
              {children}
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
