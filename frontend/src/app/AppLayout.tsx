import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import {
  CalendarIcon,
  CapIcon,
  ChevronIcon,
  FileIcon,
  HelpIcon,
  LogoutIcon,
  UserIcon,
} from '../features/booking/icons'
import type { User } from '../features/booking/types'
import { homePath } from './routes'

interface AppLayoutProps {
  user: User
  onSignOut: () => void
}

interface NavItem {
  path: string
  label: string
  icon: ReactNode
}

function DashboardIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  )
}

export function AppBrand() {
  return (
    <img className="app-brand" src="/images/unsw-logo.png" alt="UNSW Sydney" width="330" height="140" />
  )
}

export function AppLayout({ user, onSignOut }: AppLayoutProps) {
  const { pathname } = useLocation()
  const [accountOpen, setAccountOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const accountRef = useRef<HTMLDivElement>(null)
  const accountButtonRef = useRef<HTMLButtonElement>(null)
  const mobileDialogRef = useRef<HTMLDialogElement>(null)
  const isStaff = user.role === 'ADMIN' || user.role === 'MANAGER'
  const roleLabel = user.role === 'MANAGER' ? 'Manager' : user.role === 'ADMIN' ? 'Admin' : 'Student'
  const initials = (user.display_name.trim() || user.zid)
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase()

  const mainItems: NavItem[] =
  user.role === 'STUDENT'
    ? [
        {
          path: '/dashboard',
          label: 'Dashboard',
          icon: <DashboardIcon />,
        },
        {
          path: '/resources',
          label: 'Book a Resource',
          icon: <CalendarIcon />,
        },
        {
          path: '/induction',
          label: 'Induction & Training',
          icon: <CapIcon />,
        },
        {
          path: '/bookings',
          label: 'My Bookings',
          icon: <CalendarIcon />,
        },
      ]
    : []
  const staffItems: NavItem[] = isStaff ? [
    { path: '/admin/qualifications', label: 'Qualification Review', icon: <CapIcon /> },
    { path: '/admin/bookings', label: 'Booking Review', icon: <FileIcon /> },
    ...(user.role === 'MANAGER' ? [
      {
        path: '/manager/bookings',
        label: 'Room Management',
        icon: <CalendarIcon />,
      },
      {
        path: '/manager/users',
        label: 'User Management',
        icon: <UserIcon />,
      },
    ] : []),
  ] : []

  useEffect(() => {
    if (!accountOpen) return
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !accountRef.current?.contains(event.target)) {
        setAccountOpen(false)
      }
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setAccountOpen(false)
        accountButtonRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [accountOpen])

  useEffect(() => {
    if (!mobileOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const desktopMedia = window.matchMedia('(min-width: 901px)')
    const onResize = () => {
      if (desktopMedia.matches) mobileDialogRef.current?.close()
    }
    desktopMedia.addEventListener('change', onResize)
    return () => {
      document.body.style.overflow = previousOverflow
      desktopMedia.removeEventListener('change', onResize)
    }
  }, [mobileOpen])

  useEffect(() => {
    mobileDialogRef.current?.close()
  }, [pathname])

  const closeMobile = () => mobileDialogRef.current?.close()
  const navLink = (item: NavItem, mobile = false) => (
    <NavLink
      key={item.path}
      to={item.path}
      end
      caseSensitive
      className={({ isActive }) => `app-nav-link${isActive ? ' is-active' : ''}`}
      onClick={mobile ? closeMobile : undefined}
    >
      {item.icon}<span>{item.label}</span>
    </NavLink>
  )
  const sidebarContent = (mobile = false) => (
    <>
      <div className="app-sidebar-brand">
        <Link to={homePath(user.role)} aria-label="UNSW SmartLab portal home" onClick={mobile ? closeMobile : undefined}><AppBrand /></Link>
        {mobile && <button className="app-icon-button" aria-label="Close navigation" onClick={closeMobile}><span aria-hidden="true">×</span></button>}
      </div>
      <div className="app-product-label">SMARTLAB <span>RESOURCE BOOKING</span></div>
      <nav aria-label={mobile ? 'Mobile navigation' : 'Main navigation'} className="app-navigation">
        {mainItems.map((item) => navLink(item, mobile))}
        {staffItems.length > 0 && (
          <div className="app-staff-navigation">
            <p className="app-nav-label">Administration</p>
            {staffItems.map((item) => navLink(item, mobile))}
          </div>
        )}
      </nav>
      <div className="app-sidebar-footer">
        {navLink({ path: '/help', label: 'Help & Support', icon: <HelpIcon /> }, mobile)}
        <p>University spaces, made accessible.</p>
      </div>
    </>
  )

  return (
    <div className="app-shell">
      <a className="app-skip-link" href="#app-main" onClick={(event) => {
        event.preventDefault()
        document.getElementById('app-main')?.focus()
      }}>Skip to main content</a>
      <aside className="app-sidebar">{sidebarContent()}</aside>
      <dialog
        ref={mobileDialogRef}
        className="app-mobile-dialog"
        id="app-mobile-navigation"
        aria-label="Navigation"
        onClose={() => setMobileOpen(false)}
        onClick={(event) => {
          if (event.target !== event.currentTarget) return
          const bounds = event.currentTarget.getBoundingClientRect()
          if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeMobile()
        }}
      >
        {sidebarContent(true)}
      </dialog>
      <div className="app-workspace">
        <header className="app-topbar">
          <div className="app-topbar-heading">
            <button
              className="app-icon-button app-menu-toggle"
              type="button"
              aria-label="Open navigation"
              aria-expanded={mobileOpen}
              aria-controls="app-mobile-navigation"
              onClick={() => {
                setAccountOpen(false)
                mobileDialogRef.current?.showModal()
                setMobileOpen(true)
              }}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <span className="app-portal-title">{roleLabel} Portal</span>
          </div>
          <div className="app-account" ref={accountRef} onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setAccountOpen(false)
          }}>
            <button
              className="app-account-button"
              type="button"
              ref={accountButtonRef}
              aria-label={`Account options for ${user.display_name || user.zid}`}
              aria-expanded={accountOpen}
              aria-controls="app-account-actions"
              onClick={() => setAccountOpen((value) => !value)}
            >
              <span className="app-avatar" aria-hidden="true">{initials}</span>
              <span className="app-account-details"><strong>{user.display_name || user.zid}</strong><small>{roleLabel}</small></span>
              <ChevronIcon size={16} />
            </button>
            {accountOpen && (
              <div className="app-account-menu" id="app-account-actions">
                <Link to="/account" onClick={() => setAccountOpen(false)}><UserIcon size={18} />Account details</Link>
                <button type="button" onClick={() => { setAccountOpen(false); onSignOut() }}><LogoutIcon size={18} />Sign out</button>
              </div>
            )}
          </div>
        </header>
        <main className="app-content" id="app-main" tabIndex={-1}><Outlet /></main>
        <footer className="app-workspace-footer"><span>SmartLab · UNSW Sydney</span><Link to="/help">Help & Support <span aria-hidden="true">↗</span></Link></footer>
      </div>
    </div>
  )
}
