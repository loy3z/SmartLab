-- Extension requests (2026-11-07, client Week 8 meeting): the person asks to finish a booking in progress later
-- and a Manager decides. The requested end is kept on the booking until then. Run after 015. Safe to run again;
-- existing bookings get NULL (nothing waiting).

ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS extension_end timestamp with time zone;
ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_extension_end_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_extension_end_check
    CHECK (((extension_end IS NULL) OR (extension_end > "end")));
