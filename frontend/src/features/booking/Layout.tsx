import { useState, type ReactNode } from 'react'
import { CalendarIcon, CapIcon, ChevronIcon, ClockIcon, FileIcon, HelpIcon, LogoutIcon, UserIcon } from './icons'
import type { User } from './types'


export type Page = 'browse' | 'mine' | 'induction' | 'qualification-review' | 'manager-bookings' | 'booking-review'

interface Props {
  page: Page
  onNavigate: (p: Page) => void
  user: User | null
  onSignOut: () => void
  children: ReactNode
}

export function Layout({ page, onNavigate, user, onSignOut, children }: Props) {
  const [menu, setMenu] = useState(false)
  const isStaff = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const initials = (user?.display_name ?? '?')
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  // Items owned by other team members are shown disabled so the shell matches the final design.
  const items: { key: Page | null; label: string; icon: ReactNode }[] = [
    { key: 'browse', label: 'Book a Resource', icon: <CalendarIcon /> },
    { key: 'induction', label: 'Induction & Training', icon: <CapIcon /> },
    { key: null, label: 'Application Progress', icon: <FileIcon /> },
    { key: 'mine', label: 'My Bookings', icon: <CalendarIcon /> },
    { key: null, label: 'Booking History', icon: <ClockIcon /> },
  ]
  if (isStaff) {
    items.push(
      {
        key: 'qualification-review',
        label: 'Qualification Review',
        icon: <CapIcon />,
      },
      {
        key: 'booking-review',
        label: 'Booking Review',
        icon: <FileIcon />,
      },
    )
  }
  if (user?.role === 'MANAGER') {
    items.push({
      key: 'manager-bookings',
      label: 'Room Booking Management',
      icon: <CalendarIcon />,
    })
  }

  return (
    <div className="bk-shell">
      <aside className="bk-side">
        <div className="bk-brand">SmartLab<span>Booking</span></div>
        <nav>
          {items.map((i) => (
            <button
              key={i.label}
              className={`bk-nav ${i.key === page ? 'is-active' : ''}`}
              disabled={!i.key}
              title={i.key ? undefined : 'Coming soon'}
              onClick={() => i.key && onNavigate(i.key)}
            >
              {i.icon}
              {i.label}
            </button>
          ))}
        </nav>
        <button className="bk-nav bk-help" disabled>
          <HelpIcon /> Help & Support
        </button>
      </aside>
      <div className="bk-main">
        <header className="bk-top">
          <span className="bk-top-title">
            {user?.role === 'MANAGER'
              ? 'Manager Portal'
              : isStaff
                ? 'Admin Portal'
                : 'Student Portal'}
          </span>
          <div className="bk-user">
            <button className="bk-user-btn" onClick={() => setMenu((m) => !m)}>
              <span className="bk-avatar">{initials}</span>
              <span className="bk-user-text">
                <b>{user?.display_name ?? '…'}</b>
                <small>{user?.role === 'STUDENT' ? 'Student' : user?.role}</small>
              </span>
              <ChevronIcon size={16} />
            </button>
            {menu && (
              <div className="bk-menu">
                <button disabled><UserIcon size={18} /> Account Details</button>
                <button onClick={onSignOut}><LogoutIcon size={18} /> Sign Out</button>
              </div>
            )}
          </div>
        </header>
        <main className="bk-content">{children}</main>
      </div>
    </div>
  )
}
