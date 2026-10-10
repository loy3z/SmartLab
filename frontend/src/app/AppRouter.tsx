import { useEffect, useRef } from 'react'
import { useAuth } from '../features/auth/auth-context'
import { LoginPage } from '../features/auth/LoginPage'
import { BookingApp } from '../features/booking/BookingApp'
import { MyBookings } from '../features/booking/MyBookings'
import { InductionPage } from '../features/induction/InductionPage'
import { QualificationReviewPage } from '../features/admin/QualificationReviewPage'
import { BookingReviewPage } from '../features/admin/BookingReviewPage'
import { ManagerBookingsPage } from '../features/manager/ManagerBookingsPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { AppLayout } from './AppLayout'
import { AccountPage, HelpPage } from './UtilityPages'
import { navigate, usePath } from './navigation'
import { canAccess, homePath, isKnownPath } from './routes'

const titles: Record<string, string> = {
  '/dashboard': 'Dashboard', '/resources': 'Book a resource', '/bookings': 'My bookings',
  '/induction': 'Induction & training', '/admin/qualifications': 'Qualification review',
  '/admin/bookings': 'Booking review', '/manager/bookings': 'Room management',
  '/account': 'Account details', '/help': 'Help & support', '/login': 'Sign in',
}

export function AppRouter() {
  const auth = useAuth()
  const path = usePath()
  const returnPath = useRef<string | null>(null)

  useEffect(() => {
    if (auth.status === 'anonymous' && path !== '/login') {
      if (isKnownPath(path)) returnPath.current = path
      navigate('/login', true)
    } else if (auth.user && (path === '/login' || path === '/')) {
      const destination = returnPath.current
      returnPath.current = null
      navigate(destination && canAccess(destination, auth.user.role) ? destination : homePath(auth.user.role), true)
    }
  }, [auth.status, auth.user, path])

  useEffect(() => {
    document.title = `${titles[path] ?? 'SmartLab'} · UNSW SmartLab`
    if (auth.status === 'authenticated') document.getElementById('app-main')?.focus({ preventScroll: true })
  }, [path, auth.status])

  if (auth.status === 'loading') return <div className="app-session-state" role="status"><span className="app-loading-dot" />Loading your account…</div>
  if (auth.status === 'error') return <div className="app-session-state"><div className="app-card"><h1>Unable to restore your session</h1><p role="alert">{auth.error}</p><div className="app-page-actions"><button className="app-button" onClick={auth.retry}>Try again</button><button className="app-button app-button-secondary" onClick={auth.signOut}>Back to sign in</button></div></div></div>
  if (!auth.user) return <LoginPage notice={auth.notice} />
  const user = auth.user
  if (path === '/' || path === '/login') return <div className="app-session-state" role="status">Opening your portal…</div>
  const permitted = canAccess(path, user.role)
  const signOut = () => { returnPath.current = null; navigate('/login', true); auth.signOut() }

  return <AppLayout key={`${user.id}:${user.role}`} user={user} path={path} onSignOut={signOut}>
    {!permitted ? <section className="app-card app-message-page"><p className="app-eyebrow">{isKnownPath(path) ? 'ACCESS RESTRICTED' : 'PAGE NOT FOUND'}</p><h1>{isKnownPath(path) ? 'This page is not available for your role' : 'We couldn’t find that page'}</h1><p className="app-page-description">{isKnownPath(path) ? 'Use the navigation to open the pages available to your account.' : 'The link may be incorrect. Return to your portal to continue.'}</p><a className="app-button" href={`#${homePath(user.role)}`}>Return to my portal</a></section> : <div key={path}>
      {path === '/dashboard' && <DashboardPage user={user} />}
      {path === '/resources' && <BookingApp onBooked={() => navigate('/bookings')} />}
      {path === '/bookings' && <MyBookings refreshKey={0} />}
      {path === '/induction' && <InductionPage />}
      {path === '/admin/qualifications' && <QualificationReviewPage />}
      {path === '/admin/bookings' && <BookingReviewPage />}
      {path === '/manager/bookings' && <ManagerBookingsPage />}
      {path === '/account' && <AccountPage user={user} />}
      {path === '/help' && <HelpPage user={user} />}
    </div>}
  </AppLayout>
}
