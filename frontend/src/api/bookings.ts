// Sprint 3 (2026-10-27): moved from the booking feature folder; function bodies unchanged.
import { request } from '../lib/api-client'
import { post } from './client'
import type { AdditionalHoursRequest, Booking, BookingRequest, BookingSeries, Dashboard, LongBookingRequest, SeriesPlan, SeriesPreview } from './types/bookings'
import type { ListResponse } from './types/common'

export const getDashboard = () => request<Dashboard>('dashboard/')

export const createBooking = (data: BookingRequest, idempotencyKey: string) =>
  post<Booking>('bookings/', data, { 'Idempotency-Key': idempotencyKey })

export const requestAdditionalHours = (data: AdditionalHoursRequest, idempotencyKey: string) =>
  post<Booking>('bookings/additional-hours/', data, { 'Idempotency-Key': idempotencyKey })

export const requestLongBooking = (data: LongBookingRequest, idempotencyKey: string) =>
  post<Booking>('bookings/long-bookings/', data, { 'Idempotency-Key': idempotencyKey })


export const listBookings = () => request<ListResponse<Booking>>('bookings/')

export const cancelBooking = (id: string) => post<Booking>(`bookings/${id}/cancel/`, {})

// Sprint 3 (1.20.0): personal visibility only; the shared booking remains in staff records.
export const removeBookingHistory = (id: string) => post<void>(`bookings/${id}/remove-from-history/`, {})

export const rescheduleBooking = (id: string, start: string, end: string) =>
  post<Booking>(`bookings/${id}/reschedule/`, { start, end })

/** Sprint 3 (1.16.0): the person a booking is for asks for a new time; returns the new request (the old booking stays until it is approved). */
export const requestTimeChange = (id: string, start: string, end: string) =>
  post<Booking>(`bookings/${id}/change/`, { start, end })

// Sprint 3: check-in and booking freeze ---------------------------------------------------------------------------------
export const checkIn = (bookingId: string) => post<Booking>(`bookings/${bookingId}/check-in/`, {})

// Sprint 3: weekly series (staff) ---------------------------------------------------------------------------------------
export const previewSeries = (plan: SeriesPlan) => post<SeriesPreview>('bookings/series/preview/', plan)

export const createSeries = (plan: SeriesPlan & { purpose: string; skip_dates: string[] }) =>
  post<BookingSeries>('bookings/series/', plan)

export const getSeries = (id: string) => request<BookingSeries>(`bookings/series/${id}/`)

export const cancelSeries = (id: string) => post<BookingSeries>(`bookings/series/${id}/cancel/`, {})

