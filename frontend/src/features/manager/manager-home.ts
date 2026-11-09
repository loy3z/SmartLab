// 2026-11-07 (client, Week 8): helpers of the Manager home page (ManagerHomePage.tsx), kept here so they can be tested.
import type { Resource, UsageRow } from '../../api/types/index.ts'

/** 2026-11-09: one part of a split bar, e.g. "18 open"; `share` is its width as a percentage. */
export interface Segment { label: string; count: number; color: string; share: number }

/** The parts of a split bar with their widths; empty parts are left out, and nothing is returned when all are 0. */
export function segments(parts: { label: string; count: number; color: string }[]): Segment[] {
  const total = parts.reduce((sum, part) => sum + part.count, 0)
  if (total === 0) return []
  return parts.filter((part) => part.count > 0).map((part) => ({ ...part, share: (part.count / total) * 100 }))
}

/** 2026-11-09: the rooms and equipment booked most this week, with each bar's width relative to the busiest. */
export function busiest(rows: UsageRow[], limit = 6): { id: string; name: string; hours: number; share: number }[] {
  const booked = rows.filter((row) => row.booked_hours > 0).sort((a, b) => b.booked_hours - a.booked_hours || a.name.localeCompare(b.name))
  const most = booked[0]?.booked_hours ?? 0
  return booked.slice(0, limit).map((row) => ({ id: row.resource_id, name: row.name, hours: row.booked_hours, share: (row.booked_hours / most) * 100 }))
}

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
