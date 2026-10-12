-- For a local database created from the earlier schema (before 2026-10-12).
-- Brings it in line with database/schema.sql. Safe to run once; run it with psql:
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/001_client_approval_flow.sql

-- Manager room status (maintenance / closed).
ALTER TABLE public.bookable_resource
    ADD COLUMN IF NOT EXISTS status text DEFAULT 'AVAILABLE'::text NOT NULL,
    ADD COLUMN IF NOT EXISTS status_reason text;
ALTER TABLE public.bookable_resource DROP CONSTRAINT IF EXISTS bookable_resource_status_check;
ALTER TABLE public.bookable_resource ADD CONSTRAINT bookable_resource_status_check
    CHECK (((status = ANY (ARRAY['AVAILABLE'::text, 'MAINTENANCE'::text, 'CLOSED'::text]))
            AND ((status_reason IS NULL) OR (char_length(status_reason) <= 500))));

-- pending_hold_minutes is now the admin review window: 24 hours by default.
ALTER TABLE public.bookable_resource ALTER COLUMN pending_hold_minutes SET DEFAULT 1440;
UPDATE public.bookable_resource SET pending_hold_minutes = 1440 WHERE pending_hold_minutes = 30;

-- The system never stores passwords (sign-in is SSO).
ALTER TABLE public.app_users DROP COLUMN IF EXISTS passowrd;

-- Finds pending requests whose review window has ended.
CREATE INDEX IF NOT EXISTS booking_review_due_idx ON public.booking USING btree (review_due_at)
    WHERE (status = 'PENDING_APPROVAL'::text);
