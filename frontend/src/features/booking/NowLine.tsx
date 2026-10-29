// Sprint 3 (1.15.0): red "now" line drawn over a day's time cells (slot picker and Find a free time).
import { useEffect, useState } from 'react'
import { nowLineFraction } from './slot-cells'
import type { Slot } from '../../api/types/index.ts'

type Cells = Pick<Slot, 'start' | 'end'>[]

/** Current time, updated once a minute. Kept in state so rendering stays pure. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

/**
 * Put inside a `.ui-tl-grid`. Shows nothing unless the current time falls within the cells shown
 * (in practice: today, during opening hours).
 */
export function NowLine({ slots }: { slots: Cells }) {
  const fraction = nowLineFraction(slots, useNow())
  if (fraction === null) return null
  return <span className="ui-tl-now" style={{ left: `${fraction * 100}%` }} aria-hidden="true" />
}

/** Legend entry for the line; only shown when the line is. */
export function NowLegend({ slots }: { slots: Cells }) {
  return nowLineFraction(slots, useNow()) === null ? null : <span><i className="lg-now" />Now</span>
}
