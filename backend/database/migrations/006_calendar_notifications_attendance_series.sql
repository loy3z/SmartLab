-- Calendar subscription links, website notifications, check-in with booking freeze, and weekly series made by staff.
-- Run after 005. Safe to run again.
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/006_calendar_notifications_attendance_series.sql

-- Missed check-ins and booking freeze (per person).
ALTER TABLE public.app_users ADD COLUMN IF NOT EXISTS no_show_count integer DEFAULT 0 NOT NULL;
ALTER TABLE public.app_users ADD COLUMN IF NOT EXISTS frozen_until timestamp with time zone;
ALTER TABLE public.app_users DROP CONSTRAINT IF EXISTS app_users_no_show_count_check;
ALTER TABLE public.app_users ADD CONSTRAINT app_users_no_show_count_check CHECK ((no_show_count >= 0));

-- Weekly series created by staff. Each occurrence is a normal booking row with series_id.
CREATE TABLE IF NOT EXISTS public.booking_series (
    id uuid NOT NULL,
    student_id uuid NOT NULL,
    created_by uuid NOT NULL,
    resource_id uuid NOT NULL,
    weekdays text NOT NULL,
    start_time time without time zone NOT NULL,
    duration_minutes integer NOT NULL,
    first_date date NOT NULL,
    last_date date NOT NULL,
    purpose text NOT NULL,
    created_at timestamp with time zone NOT NULL
);
ALTER TABLE public.booking_series DROP CONSTRAINT IF EXISTS booking_series_rules_check;
ALTER TABLE public.booking_series ADD CONSTRAINT booking_series_rules_check
    CHECK (((weekdays ~ '^[1-7](,[1-7])*$'::text) AND (duration_minutes > 0) AND (last_date >= first_date)));

-- Booking: series and attendance. Bookings that started before check-in existed are marked NOT_TRACKED once,
-- when the column is first added, so they never count as missed.
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS series_id uuid;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'booking' AND column_name = 'attendance') THEN
        ALTER TABLE public.booking ADD COLUMN attendance text;
        UPDATE public.booking SET attendance = 'NOT_TRACKED' WHERE status = 'APPROVED' AND start < now();
    END IF;
END $$;
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS checked_in_at timestamp with time zone;
ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_attendance_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_attendance_check
    CHECK (((attendance IS NULL) OR (attendance = ANY (ARRAY['CHECKED_IN'::text, 'NO_SHOW'::text, 'EXCUSED'::text, 'NOT_TRACKED'::text]))));

-- Website notifications (delivery channels such as Outlook mail can send the same rows later).
CREATE TABLE IF NOT EXISTS public.notification (
    id uuid NOT NULL,
    recipient_id uuid NOT NULL,
    kind text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    link text,
    booking_id uuid,
    read_at timestamp with time zone
);

-- Secret calendar subscription address, one per person.
CREATE TABLE IF NOT EXISTS public.calendar_feed (
    principal_id uuid NOT NULL,
    token text NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Requests to lift a booking freeze.
CREATE TABLE IF NOT EXISTS public.unfreeze_request (
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    reason text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    decided_by uuid,
    decided_at timestamp with time zone,
    decision_reason text
);
ALTER TABLE public.unfreeze_request DROP CONSTRAINT IF EXISTS unfreeze_request_status_check;
ALTER TABLE public.unfreeze_request ADD CONSTRAINT unfreeze_request_status_check
    CHECK (((status = ANY (ARRAY['PENDING'::text, 'APPROVED'::text, 'REJECTED'::text])) AND (char_length(reason) <= 1000)));

-- Keys (dropped and added again so the script can run more than once).
ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_series_fk;
ALTER TABLE public.booking_series DROP CONSTRAINT IF EXISTS booking_series_pkey;
ALTER TABLE ONLY public.booking_series ADD CONSTRAINT booking_series_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_series_fk FOREIGN KEY (series_id) REFERENCES public.booking_series(id) ON DELETE RESTRICT;
ALTER TABLE public.booking_series DROP CONSTRAINT IF EXISTS booking_series_student_fk;
ALTER TABLE ONLY public.booking_series
    ADD CONSTRAINT booking_series_student_fk FOREIGN KEY (student_id) REFERENCES public.app_users(id) ON DELETE RESTRICT;
ALTER TABLE public.booking_series DROP CONSTRAINT IF EXISTS booking_series_created_by_fk;
ALTER TABLE ONLY public.booking_series
    ADD CONSTRAINT booking_series_created_by_fk FOREIGN KEY (created_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;
ALTER TABLE public.booking_series DROP CONSTRAINT IF EXISTS booking_series_resource_fk;
ALTER TABLE ONLY public.booking_series
    ADD CONSTRAINT booking_series_resource_fk FOREIGN KEY (resource_id) REFERENCES public.bookable_resource(id) ON DELETE RESTRICT;

ALTER TABLE public.notification DROP CONSTRAINT IF EXISTS notification_pkey;
ALTER TABLE ONLY public.notification ADD CONSTRAINT notification_pkey PRIMARY KEY (id);
ALTER TABLE public.notification DROP CONSTRAINT IF EXISTS notification_recipient_fk;
ALTER TABLE ONLY public.notification
    ADD CONSTRAINT notification_recipient_fk FOREIGN KEY (recipient_id) REFERENCES public.app_users(id) ON DELETE CASCADE;
ALTER TABLE public.notification DROP CONSTRAINT IF EXISTS notification_booking_fk;
ALTER TABLE ONLY public.notification
    ADD CONSTRAINT notification_booking_fk FOREIGN KEY (booking_id) REFERENCES public.booking(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS notification_recipient_idx ON public.notification USING btree (recipient_id, created_at DESC);

ALTER TABLE public.calendar_feed DROP CONSTRAINT IF EXISTS calendar_feed_pkey;
ALTER TABLE ONLY public.calendar_feed ADD CONSTRAINT calendar_feed_pkey PRIMARY KEY (principal_id);
ALTER TABLE public.calendar_feed DROP CONSTRAINT IF EXISTS calendar_feed_token_unique;
ALTER TABLE ONLY public.calendar_feed ADD CONSTRAINT calendar_feed_token_unique UNIQUE (token);
ALTER TABLE public.calendar_feed DROP CONSTRAINT IF EXISTS calendar_feed_principal_fk;
ALTER TABLE ONLY public.calendar_feed
    ADD CONSTRAINT calendar_feed_principal_fk FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;

ALTER TABLE public.unfreeze_request DROP CONSTRAINT IF EXISTS unfreeze_request_pkey;
ALTER TABLE ONLY public.unfreeze_request ADD CONSTRAINT unfreeze_request_pkey PRIMARY KEY (id);
ALTER TABLE public.unfreeze_request DROP CONSTRAINT IF EXISTS unfreeze_request_principal_fk;
ALTER TABLE ONLY public.unfreeze_request
    ADD CONSTRAINT unfreeze_request_principal_fk FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;
ALTER TABLE public.unfreeze_request DROP CONSTRAINT IF EXISTS unfreeze_request_decided_by_fk;
ALTER TABLE ONLY public.unfreeze_request
    ADD CONSTRAINT unfreeze_request_decided_by_fk FOREIGN KEY (decided_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;
-- At most one undecided request per person.
CREATE UNIQUE INDEX IF NOT EXISTS unfreeze_request_one_pending_idx ON public.unfreeze_request USING btree (principal_id)
    WHERE (status = 'PENDING'::text);

CREATE INDEX IF NOT EXISTS booking_series_idx ON public.booking USING btree (series_id) WHERE (series_id IS NOT NULL);
