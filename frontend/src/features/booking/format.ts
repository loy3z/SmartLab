import type { ApiError } from './api'
import type { Booking, BookingStatus, QualificationStatus } from './types'

export const TZ = 'Australia/Sydney'

export const fmtTime = (iso: string) =>
  new Intl.DateTimeFormat('en-AU', { timeStyle: 'short', timeZone: TZ }).format(new Date(iso))

export const fmtDateTime = (iso: string) =>
  new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium', timeStyle: 'short', timeZone: TZ }).format(
    new Date(iso),
  )

const dayLabel = new Intl.DateTimeFormat('en-AU', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ })
const dayKey = new Intl.DateTimeFormat('en-CA', { timeZone: TZ })

/** "Mon 19 Oct" in Sydney time. */
export const fmtDay = (iso: string) => dayLabel.format(new Date(iso))

/** "1 h 30 min", "45 min", "2 h". */
export function fmtDuration(minutes: number): string {
  const m = Math.max(0, Math.round(minutes))
  const h = Math.floor(m / 60)
  const rest = m % 60
  if (!h) return `${rest} min`
  return rest ? `${h} h ${rest} min` : `${h} h`
}

export const minutesBetween = (start: string, end: string) => (Date.parse(end) - Date.parse(start)) / 60000

/** "Mon 19 Oct · 4:00 pm – 4:30 pm" (the date is written once when both ends fall on the same day). */
export function fmtRange(start: string, end: string): string {
  const sameDay = dayKey.format(new Date(start)) === dayKey.format(new Date(end))
  return sameDay
    ? `${fmtDay(start)} · ${fmtTime(start)} – ${fmtTime(end)}`
    : `${fmtDay(start)} ${fmtTime(start)} – ${fmtDay(end)} ${fmtTime(end)}`
}

/** "in 23 h 5 min" / "5 min ago" relative to now (ms). */
export function fmtRelative(iso: string, now: number): string {
  const diff = Math.round((Date.parse(iso) - now) / 60000)
  if (Math.abs(diff) < 1) return 'just now'
  const text = Math.abs(diff) >= 2880 ? `${Math.round(Math.abs(diff) / 1440)} days` : fmtDuration(Math.abs(diff))
  return diff > 0 ? `in ${text}` : `${text} ago`
}

/** Today as YYYY-MM-DD in Sydney (resource-local date). */
export const todaySydney = () =>
  new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date())

export const STATUS_TEXT: Record<BookingStatus, string> = {
  WAITING_QUALIFICATION: 'Submitted, waiting for qualification check',  // earlier flow; no longer created
  WAITLISTED: 'Waitlisted',
  PENDING_APPROVAL: 'Waiting for admin approval',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  CANCELLED: 'Cancelled',
  EXPIRED: 'Expired',
}

/** Student-facing explanation of where a request stands, from status + reason_code (server is the source of truth). */
export function bookingDetail(b: Booking): string {
  switch (b.status) {
    case 'APPROVED':
      return b.reason_code === 'AUTO_APPROVED_AFTER_REVIEW_WINDOW'
        ? 'Your booking is confirmed. It was approved automatically because no admin decided within the review period.'
        : 'Your booking is confirmed.'
    case 'WAITING_QUALIFICATION':
      return b.hold_active && b.hold_until
        ? `This time is held for you until ${fmtDateTime(b.hold_until)}. If your induction is not approved by then, you will join the waitlist.`
        : 'Waiting for your induction to be reviewed.'
    case 'WAITLISTED': {
      const pos = b.waitlist_position ? `You are #${b.waitlist_position} on the waitlist. ` : ''
      const why =
        b.reason_code === 'TIME_CONFLICT'
            ? 'This time is already booked. '
            : b.reason_code === 'TEMPORARY_HOLD_CONFLICT'
              ? 'This time is held for an earlier request. '
              : ''
      return `${why}${pos}If the time frees up, your request moves up in submission order and goes to an admin for approval.`
    }
    case 'PENDING_APPROVAL': {
      if (b.urgent) {
        return `Urgent request: waiting for a Manager to approve it. The time is held until it starts; it is never approved automatically.`
      }
      const until = b.review_due_at ? ` until ${fmtDateTime(b.review_due_at)}` : ''
      const moved = b.reason_code === 'PROMOTED_FROM_WAITLIST' ? 'The time freed up and your request moved up the waitlist. ' : ''
      return `${moved}Waiting for an admin to approve it. The time is held for you${until}; if no admin decides by then, it is approved automatically as long as your induction is still valid and the time is free.`
    }
    case 'REJECTED':
      return b.reason_code === 'QUALIFICATION_REJECTED'
        ? 'Your induction was rejected, so this request was rejected. Resubmit your induction, then book again.'
        : b.reason_code?.startsWith('AUTO_REJECTED')
          ? `This request was rejected automatically at the end of the review period${b.decision_reason ? `: ${b.decision_reason}` : '.'}`
          : `This request was rejected${b.decision_reason ? `: ${b.decision_reason}` : '.'}`
    case 'CANCELLED':
      return 'This request was cancelled.'
    case 'EXPIRED':
      return 'The start time passed before this request was approved.'
  }
}

export const QUAL_TEXT: Record<QualificationStatus, string> = {
  NOT_CONFIGURED: 'This resource has no induction requirement set up yet and cannot be booked.',
  NOT_SUBMITTED: 'Please submit your induction documents first.',
  PENDING: 'Your induction documents are awaiting review. You can request a booking once they are verified.',
  VERIFIED: 'Induction verified.',
  REJECTED: 'Your induction was rejected. Please resubmit.',
  EXPIRED: 'Your induction has expired. Please resubmit.',
  EXPIRES_BEFORE_END: 'Your induction expires before this booking would end. Choose an earlier date or renew it first.',
  PREREQUISITE_REQUIRED: 'This resource needs an advanced induction, and you first need a current General laboratory induction.',
}

const ERROR_TEXT: Record<string, string> = {
  QUALIFICATION_REQUIRED: 'You need a valid induction for this resource before booking.',
  INVALID_TIME: 'Invalid time selected.',
  INVALID_TIME_INCREMENT: 'Time must align with the resource slot length.',
  OUTSIDE_OPENING_HOURS: 'Selected time is outside opening hours.',
  DURATION_LIMIT: 'Booking exceeds the maximum duration for this resource.',
  IDEMPOTENCY_CONFLICT: 'This request conflicted with an earlier one. Please try again.',
  DUPLICATE_BOOKING: 'You already have an active request for this resource during the selected time.',
  REQUEST_NOT_CANCELLABLE: 'This booking can no longer be cancelled (already started or closed).',
  REQUEST_NOT_RESCHEDULABLE: 'Only future approved bookings can be rescheduled.',
  BOOKING_CONFLICT: 'That time is already booked.',
  BOOKING_HOLD_CONFLICT: 'That time is temporarily held by another request.',
  TOKEN_EXPIRED: 'Session expired. Please log in again.',
  INVALID_TOKEN: 'Session expired. Please log in again.',
  REQUEST_WAITLISTED: 'This request is waitlisted and cannot be approved yet. When the time frees up it moves to Awaiting approval.',
  SELF_REVIEW_FORBIDDEN: 'You cannot review a request that is for you or that you created, or your own evidence. Ask another admin or a manager.',
  URGENT_NEEDS_MANAGER: 'Only a Manager can decide an urgent request.',
  URGENT_REASON_REQUIRED: 'Explain why the request is urgent.',
  URGENT_NOT_NEEDED: 'This time is inside the normal booking window. Turn off "Urgent" and send a normal request.',
  PERSON_NOT_FOUND: 'No account found for that zID.',
  RESOURCE_UNAVAILABLE: 'This resource is under maintenance or closed, so it cannot be booked right now.',
  RESOURCE_POLICY_NOT_CONFIGURED: 'This resource has no induction requirement set up yet. Contact a manager.',
  QUALIFICATION_NOT_VERIFIED: 'The student\'s induction is not verified, so this request cannot be approved.',
  REQUEST_NOT_REVIEWABLE: 'This request has already been decided or moved. The list has been refreshed.',
  ALREADY_REVIEWED: 'This has already been reviewed by someone else. The list has been refreshed.',
  NETWORK_ERROR: 'Unable to reach SmartLab. Check your connection and try again.',
  ACCOUNT_INACTIVE: 'That account is no longer active, so it cannot be booked for and its requests cannot be approved.',
  USE_STAFF_SIGN_IN: 'Admins and Managers sign in on the Staff sign-in page.',
  STUDENT_USES_SSO: 'Students sign in with university sign-in, not on the staff page.',
  INVALID_CREDENTIALS: 'The zID or password is not correct.',
  ACCOUNT_NOT_ACTIVATED: 'This account is not activated yet. Choose "First time? Activate your account" and use the invite code from your Manager.',
  INVALID_INVITE_CODE: 'The zID or invite code is not correct. Ask your Manager for a new code.',
  ACCOUNT_DEACTIVATED: 'This account has been deactivated. Contact a Manager.',
  LAST_MANAGER: 'At least one active Manager must remain. Add another Manager before deactivating this one.',
  SELF_MODIFICATION_FORBIDDEN: 'You cannot deactivate your own account. Ask another Manager.',
  ROLE_CHANGE_NOT_ALLOWED: 'Roles are fixed when an account is created. Add a new staff account instead.',
  PREREQUISITE_CYCLE: 'These prerequisites would form a loop.',
  FORBIDDEN: 'Your account cannot do this.',
}

/** Format a YYYY-MM-DD date for display without shifting it through UTC. */
export const fmtDate = (ymd: string) =>
  new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${ymd}T00:00:00Z`))

export function errorMessage(e: unknown): string {
  const err = e as ApiError
  const range = err?.details as
    | { earliest_date?: string; latest_date?: string; min_advance_days?: number; max_advance_days?: number }
    | undefined
  if (err?.code === 'BOOKING_TOO_SOON' && range?.earliest_date)
    return `Bookings must be made at least ${range.min_advance_days ?? 7} days in advance. The earliest date you can book is ${fmtDate(range.earliest_date)}.`
  if (err?.code === 'BOOKING_TOO_FAR_AHEAD' && range?.latest_date)
    return `Bookings can be made at most ${range.max_advance_days ?? 30} days ahead. The latest date you can book is ${fmtDate(range.latest_date)}.`
  if (err?.code === 'QUALIFICATION_REQUIRED') {
    const q = (err.details as { qualification_status?: string })?.qualification_status
    const why: Record<string, string> = {
      PENDING: 'Your induction is still being reviewed. You can request bookings once it is verified.',
      NOT_SUBMITTED: 'You have not submitted your induction for this resource yet.',
      REJECTED: 'Your induction was rejected. Please resubmit it.',
      EXPIRED: 'Your induction has expired. Please resubmit it.',
      VERIFIED: 'Your induction expires before the end of this booking. Please resubmit it or choose an earlier time.',
      EXPIRES_BEFORE_END: 'Your induction expires before the end of this booking. Please resubmit it or choose an earlier time.',
      PREREQUISITE_REQUIRED: 'You need a current General laboratory induction before booking this resource.',
    }
    return (q && why[q]) || ERROR_TEXT.QUALIFICATION_REQUIRED
  }
  if (err?.code === 'PREREQUISITE_REQUIRED')
    return err.message || 'Complete the prerequisite induction first.'
  if (err?.code && ERROR_TEXT[err.code]) return ERROR_TEXT[err.code]
  if (err?.code === 'VALIDATION_ERROR') {
    const first = Object.entries(err.details ?? {})[0]
    if (first) {
      const [field, problem] = first
      const text = Array.isArray(problem) ? String(problem[0]) : String(problem)
      return field === 'non_field_errors' ? text : `${field.replace(/_/g, ' ')}: ${text}`
    }
    return err.message || 'Please check the form and try again.'
  }
  return err?.message ?? 'Something went wrong.'
}

export const newIdempotencyKey = () => `bk-${crypto.randomUUID()}`

/** One-line confirmation shown after a request is accepted by the server. */
export function submittedMessage(b: Booking): { title: string; message: string } {
  const when = fmtRange(b.start, b.end)
  if (b.status === 'WAITLISTED') {
    return {
      title: `Added to the waitlist${b.waitlist_position ? ` (#${b.waitlist_position})` : ''}`,
      message: `${when}. That time is already taken; if it frees up, your request moves to an admin for approval.`,
    }
  }
  if (b.status === 'APPROVED') return { title: 'Booking confirmed', message: when }
  const forWhom = b.on_behalf && b.booked_for ? ` for ${b.booked_for.display_name} (${b.booked_for.zid})` : ''
  if (b.urgent) {
    return { title: `Urgent request submitted${forWhom}`, message: `${when}. A Manager must approve it before it starts.` }
  }
  if (forWhom) {
    return { title: `Request submitted${forWhom}`, message: `${when}. Waiting for approval${b.review_due_at ? ` (decided by ${fmtDateTime(b.review_due_at)})` : ''}.` }
  }
  return {
    title: 'Request submitted',
    message: `${when}. Waiting for admin approval${b.review_due_at ? ` (decided by ${fmtDateTime(b.review_due_at)})` : ''}.`,
  }
}
