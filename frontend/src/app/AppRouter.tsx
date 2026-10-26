import { startTransition, useEffect } from 'react'
import { NotificationPreferences } from '../features/notifications/NotificationPreferences' // Sprint 3 (1.19.0)
import { AnnouncementsPage } from '../features/announcements/AnnouncementsPage'
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../features/auth/auth-context'
import { LoginPage } from '../features/auth/LoginPage'
import { MockSsoPage } from '../features/auth/MockSsoPage'
import { StaffLoginPage } from '../features/auth/StaffLoginPage'
import { TestLoginPage } from '../features/auth/TestLoginPage'
import { BookingApp } from '../features/booking/BookingApp'
import { MyBookings } from '../features/booking/MyBookings'
import { InductionPage } from '../features/induction/InductionPage'
import { QualificationReviewPage } from '../features/admin/QualificationReviewPage'
import { BookingReviewPage } from '../features/admin/BookingReviewPage'
import { CalendarSyncPage } from '../features/admin/CalendarSyncPage'
// Sprint 3 pages
import { FreezesPage } from '../features/admin/FreezesPage'
import { ManagerBookingsPage } from '../features/manager/ManagerBookingsPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { AppLayout } from './AppLayout'
import { AccountPage, HelpPage } from './UtilityPages'
import { ManagerUsersPage } from '../features/manager/ManagerUsersPage'
import { ManagerResourcesPage } from '../features/manager/ManagerResourcesPage'
import { BookingRecordsPage } from '../features/records/BookingRecordsPage' // Sprint 3
import { TodayPage } from '../features/admin/TodayPage' // Sprint 3 (1.16.0)
import { LabSetupPage } from '../features/manager/LabSetupPage' // Sprint 3 (1.16.0)
import { canAccess, homePath, isKnownPath, loginDestination, normalizePath } from './routes'

// Browser-tab titles. Sprint 3 (internal-tool UI, AI-6): the same sentence-case names as the navigation and the H1.
const titles: Record<string, string> = {
  '/settings/notifications': 'Notifications', '/admin/announcements': 'Announcements', // Sprint 3 (1.19.0)
  '/dashboard': 'Dashboard', '/resources': 'Book a resource', '/bookings': 'My bookings',
  '/induction': 'Induction & training', '/admin/qualifications': 'Induction review',
  '/admin/bookings': 'Booking review', '/admin/freezes': 'Booking freezes', '/admin/calendar-sync': 'Calendar sync', '/manager/bookings': 'Room management',
  '/account': 'Account details', '/help': 'Help & support', '/login': 'Sign in',
  '/login/mock-sso': 'Demo university sign-in', '/staff/login': 'Staff sign-in', '/test/login': 'Test console',
  '/manager/users': 'User management',
  '/manager/resources': 'Resources',
  '/admin/records': 'Booking records',
  '/admin/today': 'Today', '/manager/setup': 'Lab setup', // Sprint 3 (1.16.0)
}

function useSignOut() {
  const { signOut } = useAuth()
  const navigate = useNavigate()
  return () => {
    // Router navigation and session clearing must commit together. Otherwise the
    // anonymous guard could remember the old page before the login URL updates.
    startTransition(() => {
      void navigate('/login', { replace: true, state: null })
      signOut()
    })
  }
}

// Public route: a successful login returns to an allowed deep link or the role's home.
function LoginRoute({ page = 'student' }: { page?: 'student' | 'mock-sso' | 'staff' | 'test' }) {
  const { user, notice } = useAuth()
  const location = useLocation()
  if (user) return <Navigate to={loginDestination(location.state, user.role)} replace state={null} />
  if (page === 'staff') return <StaffLoginPage notice={notice} />
  if (page === 'test') return <TestLoginPage />
  return page === 'mock-sso' ? <MockSsoPage notice={notice} /> : <LoginPage notice={notice} />
}

// All portal pages share this authentication boundary and the same layout.
function ProtectedLayout() {
  const auth = useAuth()
  const location = useLocation()
  const signOut = useSignOut()

  if (!auth.user) {
    const from = isKnownPath(normalizePath(location.pathname))
      ? `${location.pathname}${location.search}`
      : null
    return <Navigate to="/login" replace state={from ? { from } : null} />
  }

  return <AppLayout key={`${auth.user.id}:${auth.user.role}`} user={auth.user} onSignOut={signOut} />
}

function RequireAccess() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  return user && canAccess(normalizePath(pathname), user.role)
    ? <Outlet />
    : <RouteMessage restricted />
}

function RouteMessage({ restricted = false }: { restricted?: boolean }) {
  const { user } = useAuth()
  return (
    <section className="app-card app-message-page">
      {/* Sprint 3 (internal-tool UI, AI-2): no eyebrow; plain wording instead of "portal". */}
      <h1>{restricted ? 'This page is not available for your role' : 'Page not found'}</h1>
      <p className="app-page-description">
        {restricted ? 'Use the navigation to open the pages available to your account.' : 'The link may be wrong or out of date.'}
      </p>
      <Link className="app-button" to={user ? homePath(user.role) : '/login'}>{user ? `Go to ${user.role === 'STUDENT' ? 'Dashboard' : 'Today'}` : 'Sign in'}</Link>
    </section>
  )
}

export function AppRouter() {
  const auth = useAuth()
  const { pathname, search, state } = useLocation()
  const navigate = useNavigate()
  const signOut = useSignOut()
  const path = normalizePath(pathname)

  useEffect(() => {
    document.title = `${titles[path] ?? 'SmartLab'} · UNSW SmartLab`
    if (auth.status === 'authenticated') document.getElementById('app-main')?.focus({ preventScroll: true })
  }, [path, auth.status])

  if (auth.status === 'loading') {
    return <div className="app-session-state" role="status"><span className="app-loading-dot" />Loading your account…</div>
  }
  if (auth.status === 'error') {
    return (
      <div className="app-session-state">
        <div className="app-card">
          <h1>Unable to restore your session</h1>
          <p role="alert">{auth.error}</p>
          <div className="app-page-actions">
            <button className="app-button" onClick={auth.retry}>Try again</button>
            <button className="app-button app-button-secondary" onClick={signOut}>Back to sign in</button>
          </div>
        </div>
      </div>
    )
  }

  // Use one canonical address so trailing-slash links also highlight the menu.
  if (pathname !== path && (isKnownPath(path) || path === '/login' || path === '/login/mock-sso' || path === '/staff/login')) {
    return <Navigate to={{ pathname: path, search }} replace state={state} />
  }

  return (
    <Routes>
      <Route path="/login" caseSensitive element={<LoginRoute />} />
      <Route path="/login/mock-sso" caseSensitive element={<LoginRoute page="mock-sso" />} />
      <Route path="/staff/login" caseSensitive element={<LoginRoute page="staff" />} />
      <Route path="/test/login" caseSensitive element={<LoginRoute page="test" />} />
      <Route element={<ProtectedLayout />}>
        <Route index element={auth.user && <Navigate to={homePath(auth.user.role)} replace />} />
        <Route element={<RequireAccess />}>
          <Route path="/dashboard" caseSensitive element={auth.user && <DashboardPage user={auth.user} />} />
          <Route path="/resources" caseSensitive element={<BookingApp onBooked={() => { void navigate('/bookings') }} />} />
          <Route path="/bookings" caseSensitive element={<MyBookings refreshKey={0} />} />
          <Route path="/induction" caseSensitive element={<InductionPage />} />
          <Route path="/admin/today" caseSensitive element={<TodayPage />} />{/* Sprint 3 (1.16.0) */}
          <Route path="/admin/qualifications" caseSensitive element={<QualificationReviewPage />} />
          <Route path="/admin/bookings" caseSensitive element={<BookingReviewPage />} />
          {/* Sprint 3 */}
          <Route path="/admin/freezes" caseSensitive element={<FreezesPage />} />
          <Route path="/admin/calendar-sync" caseSensitive element={<CalendarSyncPage />} />
          <Route path="/manager/bookings" caseSensitive element={<ManagerBookingsPage />} />
          <Route path="/manager/users" caseSensitive element={<ManagerUsersPage />} />
          <Route path="/manager/resources" caseSensitive element={<ManagerResourcesPage />} />
          <Route path="/admin/records" caseSensitive element={<BookingRecordsPage />} />
          <Route path="/manager/setup" caseSensitive element={<LabSetupPage />} />{/* Sprint 3 (1.16.0) */}
          <Route path="/manager/usage" caseSensitive element={<Navigate to="/admin/records?tab=usage" replace />} />
          {/* Sprint 3 (1.19.0) */}
          <Route path="/settings/notifications" caseSensitive element={<NotificationPreferences />} />
          <Route path="/admin/announcements" caseSensitive element={<AnnouncementsPage />} />
          <Route path="/account" caseSensitive element={auth.user && <AccountPage user={auth.user} />} />
          <Route path="/help" caseSensitive element={auth.user && <HelpPage user={auth.user} />} />
        </Route>
        <Route path="*" element={<RouteMessage />} />
      </Route>
    </Routes>
  )
}
