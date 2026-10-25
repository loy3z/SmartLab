import type { ReactNode } from 'react'

const base = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' } as const
const mk = (d: ReactNode) => (p: { size?: number }) => (
  <svg {...base} width={p.size ?? 20} height={p.size ?? 20} aria-hidden="true">{d}</svg>
)

export const CalendarIcon = mk(<><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>)
export const CapIcon = mk(<><path d="M2 9l10-5 10 5-10 5z" /><path d="M6 11v5c3 2 9 2 12 0v-5" /></>)
export const FileIcon = mk(<><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 13h6M9 17h6" /></>)
export const ClockIcon = mk(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>)
export const HelpIcon = mk(<><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 015 .5c0 1.5-2.5 2-2.5 3.5M12 17h.01" /></>)
export const SearchIcon = mk(<><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></>)
export const PinIcon = mk(<><path d="M12 21s7-6 7-11a7 7 0 10-14 0c0 5 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></>)
export const CheckIcon = mk(<><circle cx="12" cy="12" r="9" /><path d="M8 12.5l3 3 5-6" /></>)
export const AlertIcon = mk(<><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 16.5h.01" /></>)
export const UploadIcon = mk(<><path d="M12 16V4M7 9l5-5 5 5M4 20h16" /></>)
export const DoorIcon = mk(<><path d="M6 21V4h10v17M4 21h16M13 12h.01" /></>)
export const FlaskIcon = mk(<><path d="M9 3h6M10 3v6l-5 10a1 1 0 001 1h12a1 1 0 001-1l-5-10V3" /></>)
export const UserIcon = mk(<><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4-6 8-6s7 2 8 6" /></>)
export const LogoutIcon = mk(<><path d="M9 4H5v16h4M16 8l4 4-4 4M20 12H9" /></>)
export const ChevronIcon = mk(<path d="M6 9l6 6 6-6" />)
// Sprint 3 (1.16.0): Lab Setup in the menu.
export const SlidersIcon = mk(<><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></>)
