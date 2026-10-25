import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Segmented tabs with an optional count badge, e.g. "Awaiting approval (3)". */
export function Tabs<T extends string>({ value, onChange, items, label }: {
  value: T
  onChange: (value: T) => void
  items: { key: T; label: string; count?: number | null }[]
  label: string
}) {
  return (
    <div className="ui-tabs" role="tablist" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={value === item.key}
          className={`ui-tab${value === item.key ? ' is-on' : ''}`}
          onClick={() => onChange(item.key)}
        >
          {item.label}
          {item.count != null && <span className="ui-count">{item.count}</span>}
        </button>
      ))}
    </div>
  )
}

/** Small "Updated 10s ago" label with a refresh icon button. */
export function RefreshStamp({ at, onRefresh, busy }: { at: number | null; onRefresh: () => void; busy?: boolean }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5000)
    return () => window.clearInterval(timer)
  }, [])
  const seconds = at ? Math.max(0, Math.round((now - at) / 1000)) : null
  const text = seconds == null ? 'Loading…' : seconds < 10 ? 'Updated just now' : seconds < 60 ? `Updated ${seconds}s ago` : `Updated ${Math.round(seconds / 60)} min ago`
  return (
    <div className="ui-stamp">
      <span>{busy ? 'Refreshing…' : text}</span>
      <button type="button" className="ui-icon-btn" aria-label="Refresh now" title="Refresh now" onClick={onRefresh} disabled={busy}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={busy ? 'ui-spin' : undefined}>
          <path d="M20 11a8 8 0 10-2.3 5.7" /><path d="M20 4v7h-7" />
        </svg>
      </button>
    </div>
  )
}

/** Collapsible explanation, closed by default ("How approval works"). */
export function InfoDisclosure({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="ui-info">
      <summary><span className="ui-info-icon" aria-hidden="true">i</span>{summary}</summary>
      <div className="ui-info-body">{children}</div>
    </details>
  )
}

export function EmptyState({ icon = '✓', title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="ui-empty">
      <span className="ui-empty-icon" aria-hidden="true">{typeof icon === 'string' ? <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{icon === '✓' ? <path d="m5 12 4 4L19 6" /> : icon === '+' ? <path d="M12 5v14M5 12h14" /> : <path d="M6 12h12" />}</svg> : icon}</span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action && <div className="ui-empty-action">{action}</div>}
    </div>
  )
}

/** Panel that slides in from the right with the details of one row. */
export function Drawer({ title, subtitle, onClose, children, footer }: {
  title: string
  subtitle?: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="ui-drawer-layer" onMouseDown={onClose}>
      <aside className="ui-drawer" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="ui-drawer-head">
          <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button ref={closeRef} type="button" className="ui-icon-btn" aria-label="Close details" onClick={onClose}>×</button>
        </header>
        <div className="ui-drawer-body">{children}</div>
        {footer && <footer className="ui-drawer-foot">{footer}</footer>}
      </aside>
    </div>
  )
}

/** Label / value list used inside drawers. */
export function Facts({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="ui-facts">
      {items.map((item) => (
        <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>
      ))}
    </dl>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="ui-page-head">
      <div>
        <h1>{title}</h1>
        {description && <p className="ui-page-desc">{description}</p>}
      </div>
      {actions && <div className="ui-page-actions">{actions}</div>}
    </header>
  )
}
