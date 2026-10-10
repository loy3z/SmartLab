import type { ApiError } from './api'
import type { BookingStatus, QualificationStatus } from './types'

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
  if (err?.code && ERROR_TEXT[err.code]) return ERROR_TEXT[err.code]
  if (err?.code === 'VALIDATION_ERROR') return `Validation error: ${JSON.stringify(err.details)}`
  return err?.message ?? 'Something went wrong.'
}

export const newIdempotencyKey = () => `bk-${crypto.randomUUID()}`
