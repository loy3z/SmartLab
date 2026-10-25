-- Sprint 3 (1.16.0): change requests, induction guidance, resource capacity and details, and the lab's contact details.
-- Change requests: a booking request may point at the approved booking it asks to move. The old booking stays until
-- the request is approved, then the application cancels it (services/changes.py).
-- Run after 006. Safe to run again.
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/007_change_requests_guidance_details_contact.sql

ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS replaces_id uuid;

-- Keys (dropped and added again so the script can run more than once).
ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_replaces_fk;
ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_replaces_fk FOREIGN KEY (replaces_id) REFERENCES public.booking(id) ON DELETE RESTRICT;

-- At most one undecided change request per booking (the application checks this too).
CREATE UNIQUE INDEX IF NOT EXISTS booking_one_open_change_idx ON public.booking USING btree (replaces_id)
    WHERE ((replaces_id IS NOT NULL) AND (status = ANY (ARRAY['WAITING_QUALIFICATION'::text, 'PENDING_APPROVAL'::text, 'WAITLISTED'::text])));

-- Induction guidance a Manager writes on the website (how to complete it, accepted proof, who reviews, who to ask).
ALTER TABLE public.qualification_requirement ADD COLUMN IF NOT EXISTS how_to_complete text DEFAULT ''::text NOT NULL;
ALTER TABLE public.qualification_requirement ADD COLUMN IF NOT EXISTS accepted_evidence text DEFAULT ''::text NOT NULL;
ALTER TABLE public.qualification_requirement ADD COLUMN IF NOT EXISTS reviewer text DEFAULT ''::text NOT NULL;
ALTER TABLE public.qualification_requirement ADD COLUMN IF NOT EXISTS contact text DEFAULT ''::text NOT NULL;

-- Resource information people need to choose: room capacity, and free "label: value" details for any resource.
ALTER TABLE public.bookable_resource ADD COLUMN IF NOT EXISTS capacity integer;
ALTER TABLE public.bookable_resource ADD COLUMN IF NOT EXISTS details jsonb DEFAULT '[]'::jsonb NOT NULL;
ALTER TABLE public.bookable_resource DROP CONSTRAINT IF EXISTS bookable_resource_capacity_check;
ALTER TABLE public.bookable_resource ADD CONSTRAINT bookable_resource_capacity_check
    CHECK (((capacity IS NULL) OR ((kind = 'ROOM'::text) AND (capacity >= 1) AND (capacity <= 1000))));
ALTER TABLE public.bookable_resource DROP CONSTRAINT IF EXISTS bookable_resource_details_check;
ALTER TABLE public.bookable_resource ADD CONSTRAINT bookable_resource_details_check
    CHECK ((jsonb_typeof(details) = 'array'::text));

-- The lab's contact details (one row), shown on Help, My Bookings and Induction & Training.
CREATE TABLE IF NOT EXISTS public.site_contact (
    id uuid NOT NULL,
    email text DEFAULT ''::text NOT NULL,
    phone text DEFAULT ''::text NOT NULL,
    hours text DEFAULT ''::text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone,
    updated_by uuid
);
ALTER TABLE public.site_contact DROP CONSTRAINT IF EXISTS site_contact_single_row_check;
ALTER TABLE public.site_contact ADD CONSTRAINT site_contact_single_row_check
    CHECK ((id = '00000000-0000-0000-0000-000000000c01'::uuid));
ALTER TABLE public.site_contact DROP CONSTRAINT IF EXISTS site_contact_updated_by_fk;
ALTER TABLE public.site_contact DROP CONSTRAINT IF EXISTS site_contact_pkey;
ALTER TABLE ONLY public.site_contact ADD CONSTRAINT site_contact_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.site_contact
    ADD CONSTRAINT site_contact_updated_by_fk FOREIGN KEY (updated_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;
