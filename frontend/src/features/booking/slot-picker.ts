// Sprint 3 (2026-10-25 cleanup): date helpers moved out of SlotPicker.tsx.
import { todaySydney } from './format'
import type { Availability } from '../../api/types/index.ts'

/** Shift a YYYY-MM-DD date by whole days. */
export function addDays(ymd: string, days: number): string {
  const date = new Date(`${ymd}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

/** First and last selectable dates: normal window, urgent (the days before it) or Manager reschedule (from today). */
export function dateRange(d: Availability | null, urgent: boolean, allowEarly: boolean): { earliest?: string; latest?: string } {
  if (!d) return {}
  if (d.test_bypass) return { earliest: d.earliest_date }
  if (urgent) return { earliest: todaySydney(), latest: d.earliest_date ? addDays(d.earliest_date, -1) : undefined }
  if (allowEarly) return { earliest: todaySydney(), latest: d.latest_date ?? undefined }
  return { earliest: d.earliest_date, latest: d.latest_date ?? undefined }
}
