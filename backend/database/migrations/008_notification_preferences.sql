-- Sprint 3 (2026-10-25): per-person notification category choices.
-- A missing row means the category is on, so existing accounts keep every notification by default.
-- Run after 007. Safe to run again.
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/008_notification_preferences.sql

CREATE TABLE IF NOT EXISTS public.notification_preference (
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    category text NOT NULL,
    enabled boolean DEFAULT true NOT NULL
);

-- Categories a person may turn off (the Managers' urgent-request notice is not one of them).
ALTER TABLE public.notification_preference DROP CONSTRAINT IF EXISTS notification_preference_category_check;
ALTER TABLE public.notification_preference ADD CONSTRAINT notification_preference_category_check
    CHECK (category = ANY (ARRAY['bookings'::text, 'reminders'::text, 'induction'::text, 'account'::text, 'resources'::text]));

-- Keys (dropped and added again so the script can run more than once).
ALTER TABLE public.notification_preference DROP CONSTRAINT IF EXISTS notification_preference_pkey;
ALTER TABLE ONLY public.notification_preference ADD CONSTRAINT notification_preference_pkey PRIMARY KEY (id);

ALTER TABLE public.notification_preference DROP CONSTRAINT IF EXISTS notification_preference_principal_fk;
ALTER TABLE ONLY public.notification_preference
    ADD CONSTRAINT notification_preference_principal_fk FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;

-- One row per person and category; saving again updates it.
CREATE UNIQUE INDEX IF NOT EXISTS notification_preference_person_category_idx
    ON public.notification_preference USING btree (principal_id, category);
