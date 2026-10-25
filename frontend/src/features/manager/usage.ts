// Sprint 3: display helpers for the Manager's usage report.
import type { UsageRow } from '../booking/types.ts'

/** 0.256 -> "26%"; null -> "—". */
export function percent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

/** Rows to look at first: most booked hours, then name. */
export function sortUsage(rows: UsageRow[]): UsageRow[] {
  return [...rows].sort((a, b) => b.booked_hours - a.booked_hours || a.name.localeCompare(b.name))
}

/** Default range: the last 28 days up to today (local dates as YYYY-MM-DD). */
export function lastFourWeeks(today: string): { first: string; last: string } {
  const date = new Date(`${today}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() - 27)
  return { first: date.toISOString().slice(0, 10), last: today }
}
