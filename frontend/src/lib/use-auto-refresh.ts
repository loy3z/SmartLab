// 2026-11-07 (three-role walkthrough): pages that show what another person decides reload by themselves, so a
// student sees the approval and an Admin sees a new request without pressing F5.
import { useEffect, useRef } from 'react'

/** Every AUTO_REFRESH_MS while the tab is visible, and again when the person comes back to the tab. */
export const AUTO_REFRESH_MS = 30_000

export function useAutoRefresh(refresh: () => void, ms = AUTO_REFRESH_MS) {
  const latest = useRef(refresh)
  useEffect(() => { latest.current = refresh })

  useEffect(() => {
    const run = () => { if (document.visibilityState === 'visible') latest.current() }
    const timer = window.setInterval(run, ms)
    window.addEventListener('focus', run)
    document.addEventListener('visibilitychange', run)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', run)
      document.removeEventListener('visibilitychange', run)
    }
  }, [ms])
}
