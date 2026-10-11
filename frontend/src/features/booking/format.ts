import type { ApiError } from './api'
import type { Booking, BookingStatus, QualificationStatus } from './types'

export const TZ = 'Australia/Sydney'

export const fmtTime = (iso: string) =>
  new Intl.DateTimeFormat('en-AU', { timeStyle: 'short', timeZone: TZ }).format(new Date(iso))

export const fmtDateTime = (iso: string) =>
  new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium', timeStyle: 'short', timeZone: TZ }).format(
    new Date(iso),
  )

/** Today as YYYY-MM-DD in Sydney (resource-local date). */
export const todaySydney = () =>
  new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date())

export const STATUS_TEXT: Record<BookingStatus, string> = {
  WAITING_QUALIFICATION: 'Submitted, waiting for qualification check',
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
      return b.reason_code === 'PROMOTED_FROM_WAITLIST'
        ? 'The time freed up and your waitlisted request was approved automatically.'
        : 'Your booking is confirmed.'
    case 'WAITING_QUALIFICATION':
      return b.hold_active && b.hold_until
        ? `This time is held for you until ${fmtDateTime(b.hold_until)}. If your induction is not approved by then, you will join the waitlist.`
        : 'Waiting for your induction to be reviewed.'
    case 'WAITLISTED': {
      const pos = b.waitlist_position ? `You are #${b.waitlist_position} on the waitlist. ` : ''
      const why =
        b.reason_code === 'HOLD_EXPIRED'
          ? 'Your hold expired before your induction was approved. '
          : b.reason_code === 'TIME_CONFLICT'
            ? 'This time is already booked. '
            : b.reason_code === 'TEMPORARY_HOLD_CONFLICT'
              ? 'This time is held for an earlier request. '
              : ''
      return `${why}${pos}You will be approved automatically if the time frees up and your induction is valid.`
    }
    case 'PENDING_APPROVAL':
      return 'Waiting for an admin to review this request.'
    case 'REJECTED':
      return b.reason_code === 'QUALIFICATION_REJECTED'
        ? 'Your induction was rejected, so this request was rejected. Resubmit your induction, then book again.'
        : 'This request was rejected.'
    case 'CANCELLED':
      return 'This request was cancelled.'
    case 'EXPIRED':
      return 'The start time passed before this request was approved.'
  }
}

export const QUAL_TEXT: Record<QualificationStatus, string> = {
  NOT_CONFIGURED: 'This resource has no induction requirement set up yet and cannot be booked.',
  NOT_SUBMITTED: 'Please submit your induction documents first.',
  PENDING: 'Your induction documents are awaiting review. You can still request a booking.',
  VERIFIED: 'Induction verified.',
  REJECTED: 'Your induction was rejected. Please resubmit.',
  EXPIRED: 'Your induction has expired. Please resubmit.',
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
  REQUEST_WAITLISTED: 'This request is waitlisted and cannot be manually approved. It will be approved automatically when eligible and the slot is available.',
  PENDING_REQUEST_LIMIT: 'Your induction is still under review, so you can only have one open request. Wait for the review or cancel the existing request.',
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
      NOT_SUBMITTED: 'You have not submitted your induction for this resource yet.',
      REJECTED: 'Your induction was rejected. Please resubmit it.',
      EXPIRED: 'Your induction has expired. Please resubmit it.',
      VERIFIED: 'Your induction expires before the end of this booking. Please resubmit it or choose an earlier time.',
    }
    return (q && why[q]) || ERROR_TEXT.QUALIFICATION_REQUIRED
  }
  if (err?.code && ERROR_TEXT[err.code]) return ERROR_TEXT[err.code]
  if (err?.code === 'VALIDATION_ERROR') return `Validation error: ${JSON.stringify(err.details)}`
  return err?.message ?? 'Something went wrong.'
}

export const newIdempotencyKey = () => `bk-${crypto.randomUUID()}`
