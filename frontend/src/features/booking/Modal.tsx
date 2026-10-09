import { useEffect, type ReactNode } from 'react'

export function Modal({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="bk-overlay" onMouseDown={onClose}>
      <div className="bk-modal" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}>
        <button className="bk-close" aria-label="Close" onClick={onClose}>×</button>
        {children}
      </div>
    </div>
  )
}
