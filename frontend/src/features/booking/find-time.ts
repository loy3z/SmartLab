// Sprint 3 (1.16.0): wording for "Find a free time" when rows are hidden (lengths and empty results).

/**
 * Booking lengths offered by Find a free time: half hours up to 3 h, then whole hours, up to the longest
 * normal booking allowed (from the server, so a changed limit needs no code change). 3 h is the default limit.
 */
export function findDurations(longestMinutes = 180) {
  return [30, 60, 90, 120, 150, 180, 240, 300, 360, 420, 480].filter(minutes => minutes <= longestMinutes)
}

const REASON_TEXT: Record<string, string> = {
  NOT_SUBMITTED: 'induction not submitted',
  PENDING: 'induction waiting for review',
  REJECTED: 'induction rejected',
  EXPIRED: 'induction expired',
  EXPIRES_BEFORE_END: 'induction expires before that day',
  PREREQUISITE_REQUIRED: 'an earlier induction is needed first',
  NOT_CONFIGURED: 'not open for booking yet',
  MAINTENANCE: 'under maintenance',
  CLOSED: 'closed',
}

/** Reasons that the person can fix on the Induction & Training page. */
const INDUCTION_REASONS = ['NOT_SUBMITTED', 'PENDING', 'REJECTED', 'EXPIRED', 'EXPIRES_BEFORE_END', 'PREREQUISITE_REQUIRED']

/**
 * Why rows were hidden by "Only show what I can book now", most common first, e.g.
 * "20 hidden: 18 induction not submitted, 2 under maintenance". needsInduction says whether to link to the induction page.
 */
export function hiddenSummary(reasons: Record<string, number> | undefined): { text: string; needsInduction: boolean } {
  const entries = Object.entries(reasons ?? {}).filter(([, count]) => count > 0).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  if (entries.length === 0) return { text: '', needsInduction: false }
  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  const parts = entries.map(([reason, count]) => `${count} ${REASON_TEXT[reason] ?? reason.replaceAll('_', ' ').toLowerCase()}`)
  return { text: `${total} hidden: ${parts.join(', ')}`, needsInduction: entries.some(([reason]) => INDUCTION_REASONS.includes(reason)) }
}
