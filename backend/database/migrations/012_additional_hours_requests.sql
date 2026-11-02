-- Additional weekly hours requests (2026-11-02). Run after 011 before starting the new backend.
-- Safe to run again. Existing bookings retain their fields and receive false/null defaults.
-- A Manager may approve these requests only within 48 hours before the booking start. They never acquire a
-- pending hold or an automatic-review deadline; only APPROVED records block resource time.
-- An undecided request expires when its requested booking starts.
-- reviewed_by/reviewed_at and start/end retain the exact approved scope. Priority at the time
-- of the decision is recorded in the append-only audit trail, not as a mutable booking rank.

ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS additional_hours boolean DEFAULT false NOT NULL;
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS additional_hours_reason text;
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS active_data_collection boolean DEFAULT false NOT NULL;
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS data_collection_reason text;

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_additional_hours_reason_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_additional_hours_reason_check
    CHECK ((NOT additional_hours OR NULLIF(btrim(additional_hours_reason), '') IS NOT NULL));

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_data_collection_reason_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_data_collection_reason_check
    CHECK ((NOT active_data_collection OR (additional_hours AND NULLIF(btrim(data_collection_reason), '') IS NOT NULL)));

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_additional_hours_no_hold_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_additional_hours_no_hold_check
    CHECK ((NOT additional_hours OR (hold_until IS NULL AND review_due_at IS NULL)));

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_additional_hours_not_urgent_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_additional_hours_not_urgent_check
    CHECK ((NOT additional_hours OR NOT urgent));
