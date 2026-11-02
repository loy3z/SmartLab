-- Long-duration requests (2026-11-03). Apply 012 first, then this migration before the new backend starts.
-- Safe to run again. Existing ordinary and additional-hours bookings receive false/null defaults;
-- their status, requested time, review metadata and pending holds are unchanged.
-- A long request needs a reason and a Manager's explicit decision. It remains subject to ordinary
-- pending holds and FIFO waitlisting, so hold_until/review_due_at are deliberately allowed.
-- Long requests cannot also be urgent, additional weekly hours, or a weekly-series occurrence.

ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS long_booking boolean DEFAULT false NOT NULL;
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS long_booking_reason text;

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_long_booking_reason_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_long_booking_reason_check
    CHECK ((NOT long_booking OR NULLIF(btrim(long_booking_reason), '') IS NOT NULL));

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_long_booking_kind_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_long_booking_kind_check
    CHECK ((NOT long_booking OR (NOT urgent AND NOT additional_hours AND series_id IS NULL)));
