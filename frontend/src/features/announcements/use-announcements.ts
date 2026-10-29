// Sprint 3 (fluency V5): home pages wait for the first announcement result, including failure.
import { useEffect, useState } from 'react'
import { listAnnouncements } from '../../api/index.ts'
import { errorMessage } from '../booking/format'
import type { Announcement } from '../../api/types/index.ts'

export function useAnnouncements() {
  const [state, setState] = useState<{ items: Announcement[]; error: string; settled: boolean }>({ items: [], error: '', settled: false })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    listAnnouncements()
      .then(data => { if (active) setState({ items: data.results, error: '', settled: true }) })
      .catch(reason => { if (active) setState({ items: [], error: errorMessage(reason), settled: true }) })
    return () => { active = false }
  }, [attempt])
  // A user-requested retry keeps an already visible home in place.
  return { ...state, retry: () => setAttempt(value => value + 1) }
}
