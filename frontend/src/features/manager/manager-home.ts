// 2026-11-07 (client, Week 8): helpers of the Manager home page (ManagerHomePage.tsx), kept here so they can be tested.
import type { Resource } from '../../api/types/index.ts'

/** Monday and Sunday (YYYY-MM-DD) of the Sydney week that contains `today`. */
export function currentWeek(today: string): { first: string; last: string } {
  const date = new Date(`${today}T00:00:00Z`)
  const fromMonday = (date.getUTCDay() + 6) % 7
  const shift = (days: number) => new Date(date.getTime() + days * 86400000).toISOString().slice(0, 10)
  return { first: shift(-fromMonday), last: shift(6 - fromMonday) }
}

/** How many listed rooms and pieces of equipment are open, under maintenance or closed. */
export function statusCounts(resources: Resource[]): Record<Resource['status'], number> {
  const counts: Record<Resource['status'], number> = { AVAILABLE: 0, MAINTENANCE: 0, CLOSED: 0 }
  for (const item of resources) if (item.active) counts[item.status] += 1
  return counts
}

/** A zID typed in the history lookup: z followed by 7 digits (case and spaces ignored), or null. */
export function cleanZid(text: string): string | null {
  const zid = text.trim().toLowerCase()
  return /^z\d{7}$/.test(zid) ? zid : null
}
