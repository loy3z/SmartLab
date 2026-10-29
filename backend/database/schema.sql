--
-- PostgreSQL database dump
--

\restrict RFnq4Lcuo0qu5mjdAilspMYGCvAqoclsEh9CVV7p0jEAIdzLaGy3BEEUunfwWD6

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: reject_audit_record_mutation(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.reject_audit_record_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION
        'Audit records are append-only. Operation % is not allowed.',
        TG_OP;
    RETURN NULL;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: app_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    zid text NOT NULL,
    display_name text NOT NULL,
    role text NOT NULL,
    university_email text CONSTRAINT app_users_email_not_null NOT NULL,
    active boolean DEFAULT true NOT NULL,
    no_show_count integer DEFAULT 0 NOT NULL,
    frozen_until timestamp with time zone,
    CONSTRAINT app_users_no_show_count_check CHECK ((no_show_count >= 0)),
    CONSTRAINT app_users_role_check CHECK ((role = ANY (ARRAY['STUDENT'::text, 'ADMIN'::text, 'MANAGER'::text])))
);


--
-- Name: audit_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_record (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    actor_id text NOT NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    at timestamp with time zone NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT audit_record_details_check CHECK ((jsonb_typeof(details) = 'object'::text))
);


--
-- Name: bookable_resource; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bookable_resource (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    kind text NOT NULL,
    location text DEFAULT ''::text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    active boolean DEFAULT true NOT NULL,
    required_qualification_id uuid,
    slot_minutes integer NOT NULL,
    max_booking_minutes integer NOT NULL,
    opening_time time without time zone NOT NULL,
    closing_time time without time zone NOT NULL,
    timezone text DEFAULT 'Australia/Sydney'::text NOT NULL,
    pending_hold_minutes integer DEFAULT 1440 NOT NULL,
    status text DEFAULT 'AVAILABLE'::text NOT NULL,
    status_reason text,
    room_id uuid,
    category text,
    capacity integer,
    details jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT bookable_resource_capacity_check CHECK (((capacity IS NULL) OR ((kind = 'ROOM'::text) AND (capacity >= 1) AND (capacity <= 1000)))),
    CONSTRAINT bookable_resource_details_check CHECK ((jsonb_typeof(details) = 'array'::text)),
    CONSTRAINT bookable_resource_room_check CHECK (((room_id IS NULL) OR (kind = 'EQUIPMENT'::text))),
    CONSTRAINT bookable_resource_status_check CHECK (((status = ANY (ARRAY['AVAILABLE'::text, 'MAINTENANCE'::text, 'CLOSED'::text])) AND ((status_reason IS NULL) OR (char_length(status_reason) <= 500)))),
    CONSTRAINT bookable_resource_rules_check CHECK (((kind = ANY (ARRAY['ROOM'::text, 'EQUIPMENT'::text])) AND (slot_minutes > 0) AND (max_booking_minutes > 0) AND (closing_time > opening_time) AND ((pending_hold_minutes >= 1) AND (pending_hold_minutes <= 20160)))),
    CONSTRAINT bookable_resource_category_check CHECK (((category IS NULL) OR ((char_length(category) >= 1) AND (char_length(category) <= 60))))
);


--
-- Name: booking; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.booking (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    student_id uuid NOT NULL,
    resource_id uuid NOT NULL,
    start timestamp with time zone NOT NULL,
    "end" timestamp with time zone NOT NULL,
    purpose text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    status text NOT NULL,
    reason_code text,
    review_due_at timestamp with time zone,
    reviewed_by text,
    reviewed_at timestamp with time zone,
    decision_reason text,
    updated_at timestamp with time zone,
    revision integer DEFAULT 1 NOT NULL,
    hold_until timestamp with time zone,
    created_by uuid,
    urgent boolean DEFAULT false NOT NULL,
    urgent_reason text,
    series_id uuid,
    attendance text,
    checked_in_at timestamp with time zone,
    replaces_id uuid,
    CONSTRAINT booking_attendance_check CHECK (((attendance IS NULL) OR (attendance = ANY (ARRAY['CHECKED_IN'::text, 'NO_SHOW'::text, 'EXCUSED'::text, 'NOT_TRACKED'::text])))),
    CONSTRAINT booking_revision_check CHECK ((revision >= 1)),
    CONSTRAINT booking_status_check CHECK ((status = ANY (ARRAY['WAITING_QUALIFICATION'::text, 'PENDING_APPROVAL'::text, 'WAITLISTED'::text, 'APPROVED'::text, 'REJECTED'::text, 'CANCELLED'::text, 'EXPIRED'::text]))),
    CONSTRAINT booking_time_check CHECK (("end" > start))
);


--
-- Name: outlook_sync_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.outlook_sync_record (
    booking_id uuid NOT NULL,
    action text NOT NULL,
    status text NOT NULL,
    calendar_path text NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    booking_revision integer DEFAULT 1 NOT NULL,
    event_id text,
    web_link text,
    ical_uid text,
    attempts integer DEFAULT 0 NOT NULL,
    create_attempted boolean DEFAULT false NOT NULL,
    next_attempt_at timestamp with time zone,
    lease_until timestamp with time zone,
    last_error text,
    last_success_at timestamp with time zone,
    CONSTRAINT outlook_sync_action_check CHECK ((action = ANY (ARRAY['CREATE'::text, 'UPDATE'::text, 'DELETE'::text]))),
    CONSTRAINT outlook_sync_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT outlook_sync_revision_check CHECK (((revision >= 1) AND (booking_revision >= 1))),
    CONSTRAINT outlook_sync_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'IN_PROGRESS'::text, 'SYNCED'::text, 'FAILED'::text])))
);


--
-- Name: qualification_requirement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.qualification_requirement (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    prerequisite_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    how_to_complete text DEFAULT ''::text NOT NULL,
    accepted_evidence text DEFAULT ''::text NOT NULL,
    reviewer text DEFAULT ''::text NOT NULL,
    contact text DEFAULT ''::text NOT NULL,
    CONSTRAINT qualification_requirement_not_own_prerequisite CHECK ((NOT (id = ANY (prerequisite_ids))))
);


--
-- Name: qualification_submission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.qualification_submission (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    student_id uuid NOT NULL,
    requirement_id uuid NOT NULL,
    title text NOT NULL,
    notes text DEFAULT ''::text NOT NULL,
    file_id uuid NOT NULL,
    submitted_at timestamp with time zone NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    reviewed_by text,
    reviewed_at timestamp with time zone,
    rejection_reason text,
    valid_until timestamp with time zone,
    storage_order bigint NOT NULL,
    CONSTRAINT qualification_submission_status_check CHECK ((status = ANY (ARRAY['PENDING'::text, 'VERIFIED'::text, 'REJECTED'::text]))),
    CONSTRAINT qualification_submission_validity_check CHECK ((((status = 'VERIFIED'::text) AND (valid_until IS NOT NULL)) OR ((status = ANY (ARRAY['PENDING'::text, 'REJECTED'::text])) AND (valid_until IS NULL))))
);


--
-- Name: qualification_submission_storage_order_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.qualification_submission ALTER COLUMN storage_order ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.qualification_submission_storage_order_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: stored_file; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stored_file (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    original_name text NOT NULL,
    content_type text NOT NULL,
    size bigint NOT NULL,
    owner_id uuid NOT NULL,
    data bytea NOT NULL,
    CONSTRAINT stored_file_size_check CHECK (((size >= 0) AND (size = octet_length(data))))
);


--
-- Name: TABLE stored_file; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.stored_file IS 'for instruction';


--
-- Name: CONSTRAINT stored_file_size_check ON stored_file; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT stored_file_size_check ON public.stored_file IS 'must have data';


--
-- Name: app_users app_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_pkey PRIMARY KEY (id);


--
-- Name: app_users app_users_zid_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_users
    ADD CONSTRAINT app_users_zid_unique UNIQUE (zid);


--
-- Name: audit_record audit_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_record
    ADD CONSTRAINT audit_record_pkey PRIMARY KEY (id);


--
-- Name: bookable_resource bookable_resource_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookable_resource
    ADD CONSTRAINT bookable_resource_pkey PRIMARY KEY (id);


--
-- Name: booking booking_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_pkey PRIMARY KEY (id);


--
-- Name: outlook_sync_record outlook_sync_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outlook_sync_record
    ADD CONSTRAINT outlook_sync_record_pkey PRIMARY KEY (booking_id);


--
-- Name: qualification_requirement qualification_requirement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qualification_requirement
    ADD CONSTRAINT qualification_requirement_pkey PRIMARY KEY (id);


--
-- Name: qualification_submission qualification_submission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qualification_submission
    ADD CONSTRAINT qualification_submission_pkey PRIMARY KEY (id);


--
-- Name: stored_file stored_file_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stored_file
    ADD CONSTRAINT stored_file_pkey PRIMARY KEY (id);


--
-- Name: audit_record_action_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_record_action_idx ON public.audit_record USING btree (action);


--
-- Name: audit_record_actor_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_record_actor_idx ON public.audit_record USING btree (actor_id);


--
-- Name: audit_record_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_record_at_idx ON public.audit_record USING btree (at DESC);


--
-- Name: audit_record_entity_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_record_entity_idx ON public.audit_record USING btree (entity_type, entity_id);


--
-- Name: booking_pending_hold_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX booking_pending_hold_idx ON public.booking USING btree (hold_until) WHERE (status = ANY (ARRAY['WAITING_QUALIFICATION'::text, 'PENDING_APPROVAL'::text]));


--
-- Name: booking_review_due_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX booking_review_due_idx ON public.booking USING btree (review_due_at) WHERE (status = 'PENDING_APPROVAL'::text);


--
-- Name: booking_resource_queue_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX booking_resource_queue_idx ON public.booking USING btree (resource_id, status, created_at, id);


--
-- Name: booking_resource_time_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX booking_resource_time_idx ON public.booking USING btree (resource_id, start, "end");


--
-- Name: booking_student_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX booking_student_status_idx ON public.booking USING btree (student_id, status);


--
-- Name: fki_bookable_resource_qualification_fkey; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fki_bookable_resource_qualification_fkey ON public.bookable_resource USING btree (required_qualification_id);


--
-- Name: fki_stored_file_owner_fkey; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX fki_stored_file_owner_fkey ON public.stored_file USING btree (owner_id);


--
-- Name: outlook_sync_retry_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX outlook_sync_retry_idx ON public.outlook_sync_record USING btree (next_attempt_at, lease_until) WHERE (status <> 'SYNCED'::text);


--
-- Name: qualification_submission_file_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX qualification_submission_file_idx ON public.qualification_submission USING btree (file_id);


--
-- Name: qualification_submission_requirement_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX qualification_submission_requirement_idx ON public.qualification_submission USING btree (requirement_id);


--
-- Name: qualification_submission_student_requirement_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX qualification_submission_student_requirement_idx ON public.qualification_submission USING btree (student_id, requirement_id, submitted_at DESC);


--
-- Name: audit_record audit_record_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER audit_record_append_only BEFORE DELETE OR UPDATE OR TRUNCATE ON public.audit_record FOR EACH STATEMENT EXECUTE FUNCTION public.reject_audit_record_mutation();


--
-- Name: bookable_resource bookable_resource_qualification_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookable_resource
    ADD CONSTRAINT bookable_resource_qualification_fkey FOREIGN KEY (required_qualification_id) REFERENCES public.qualification_requirement(id) ON DELETE RESTRICT;


--
-- Name: booking booking_resource_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bookable_resource
    ADD CONSTRAINT bookable_resource_room_fkey FOREIGN KEY (room_id) REFERENCES public.bookable_resource(id) ON DELETE RESTRICT;


--
-- Name: booking booking_resource_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_resource_fk FOREIGN KEY (resource_id) REFERENCES public.bookable_resource(id) ON DELETE RESTRICT;


--
-- Name: booking booking_student_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_student_fk FOREIGN KEY (student_id) REFERENCES public.app_users(id) ON DELETE RESTRICT;


--
-- Name: booking booking_created_by_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_created_by_fk FOREIGN KEY (created_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;


--
-- Name: outlook_sync_record outlook_sync_booking_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outlook_sync_record
    ADD CONSTRAINT outlook_sync_booking_fk FOREIGN KEY (booking_id) REFERENCES public.booking(id) ON DELETE RESTRICT;


--
-- Name: qualification_submission qualification_submission_file_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qualification_submission
    ADD CONSTRAINT qualification_submission_file_fk FOREIGN KEY (file_id) REFERENCES public.stored_file(id) ON DELETE RESTRICT;


--
-- Name: qualification_submission qualification_submission_requirement_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qualification_submission
    ADD CONSTRAINT qualification_submission_requirement_fk FOREIGN KEY (requirement_id) REFERENCES public.qualification_requirement(id) ON DELETE RESTRICT;


--
-- Name: qualification_submission qualification_submission_student_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qualification_submission
    ADD CONSTRAINT qualification_submission_student_fk FOREIGN KEY (student_id) REFERENCES public.app_users(id) ON DELETE RESTRICT;


--
-- Name: stored_file stored_file_owner_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stored_file
    ADD CONSTRAINT stored_file_owner_fkey FOREIGN KEY (owner_id) REFERENCES public.app_users(id) ON DELETE RESTRICT;


--
-- Name: staff_credential; Type: TABLE; Schema: public; Owner: -
-- How Admins and Managers sign in on the staff page (students use university sign-in and have no row).
-- password_hash is a Django password hash; invite_code is set until the account is activated.
--

CREATE TABLE public.staff_credential (
    principal_id uuid NOT NULL,
    password_hash text,
    invite_code text,
    updated_at timestamp with time zone
);

ALTER TABLE ONLY public.staff_credential
    ADD CONSTRAINT staff_credential_pkey PRIMARY KEY (principal_id);

ALTER TABLE ONLY public.staff_credential
    ADD CONSTRAINT staff_credential_principal_fkey FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;


--
-- Sprint 3 tables (see migrations/006_calendar_notifications_attendance_series.sql)
--

-- Weekly series created by staff. Each occurrence is a normal booking row with series_id.
CREATE TABLE public.booking_series (
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
ALTER TABLE public.booking_series ADD CONSTRAINT booking_series_rules_check
    CHECK (((weekdays ~ '^[1-7](,[1-7])*$'::text) AND (duration_minutes > 0) AND (last_date >= first_date)));


-- Website notifications (delivery channels such as Outlook mail can send the same rows later).
CREATE TABLE public.notification (
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

-- Durable SMTP outbox. The message snapshot is committed with the notification and sent after commit.
CREATE TABLE public.email_delivery (
    notification_id uuid NOT NULL,
    recipient_email text NOT NULL,
    subject text NOT NULL,
    body text NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp with time zone,
    lease_until timestamp with time zone,
    worker_id text,
    last_error text,
    sent_at timestamp with time zone,
    CONSTRAINT email_delivery_attempts_check CHECK (attempts >= 0),
    CONSTRAINT email_delivery_status_check CHECK (status = ANY
        (ARRAY['PENDING'::text, 'IN_PROGRESS'::text, 'RETRY'::text, 'SENT'::text, 'FAILED'::text])),
    CONSTRAINT email_delivery_state_check CHECK (
        (status = 'PENDING' AND next_attempt_at IS NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NULL) OR
        (status = 'IN_PROGRESS' AND lease_until IS NOT NULL AND worker_id IS NOT NULL AND sent_at IS NULL) OR
        (status = 'RETRY' AND next_attempt_at IS NOT NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NULL) OR
        (status = 'SENT' AND next_attempt_at IS NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NOT NULL) OR
        (status = 'FAILED' AND next_attempt_at IS NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NULL)
    )
);

-- Secret calendar subscription address, one per person.
CREATE TABLE public.calendar_feed (
    principal_id uuid NOT NULL,
    token text NOT NULL,
    created_at timestamp with time zone NOT NULL
);

-- Requests to lift a booking freeze.
CREATE TABLE public.unfreeze_request (
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    reason text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    status text DEFAULT 'PENDING'::text NOT NULL,
    decided_by uuid,
    decided_at timestamp with time zone,
    decision_reason text
);
ALTER TABLE public.unfreeze_request ADD CONSTRAINT unfreeze_request_status_check
    CHECK (((status = ANY (ARRAY['PENDING'::text, 'APPROVED'::text, 'REJECTED'::text])) AND (char_length(reason) <= 1000)));

-- Keys.
ALTER TABLE ONLY public.booking_series ADD CONSTRAINT booking_series_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_series_fk FOREIGN KEY (series_id) REFERENCES public.booking_series(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.booking_series
    ADD CONSTRAINT booking_series_student_fk FOREIGN KEY (student_id) REFERENCES public.app_users(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.booking_series
    ADD CONSTRAINT booking_series_created_by_fk FOREIGN KEY (created_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.booking_series
    ADD CONSTRAINT booking_series_resource_fk FOREIGN KEY (resource_id) REFERENCES public.bookable_resource(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.notification ADD CONSTRAINT notification_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.notification
    ADD CONSTRAINT notification_recipient_fk FOREIGN KEY (recipient_id) REFERENCES public.app_users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.notification
    ADD CONSTRAINT notification_booking_fk FOREIGN KEY (booking_id) REFERENCES public.booking(id) ON DELETE CASCADE;
CREATE INDEX notification_recipient_idx ON public.notification USING btree (recipient_id, created_at DESC);

ALTER TABLE ONLY public.email_delivery ADD CONSTRAINT email_delivery_pkey PRIMARY KEY (notification_id);
ALTER TABLE ONLY public.email_delivery
    ADD CONSTRAINT email_delivery_notification_fk FOREIGN KEY (notification_id) REFERENCES public.notification(id) ON DELETE CASCADE;
CREATE INDEX email_delivery_due_idx ON public.email_delivery USING btree (next_attempt_at, lease_until, created_at)
    WHERE status IN ('PENDING', 'IN_PROGRESS', 'RETRY');

ALTER TABLE ONLY public.calendar_feed ADD CONSTRAINT calendar_feed_pkey PRIMARY KEY (principal_id);
ALTER TABLE ONLY public.calendar_feed ADD CONSTRAINT calendar_feed_token_unique UNIQUE (token);
ALTER TABLE ONLY public.calendar_feed
    ADD CONSTRAINT calendar_feed_principal_fk FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.unfreeze_request ADD CONSTRAINT unfreeze_request_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.unfreeze_request
    ADD CONSTRAINT unfreeze_request_principal_fk FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.unfreeze_request
    ADD CONSTRAINT unfreeze_request_decided_by_fk FOREIGN KEY (decided_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;
-- At most one undecided request per person.
CREATE UNIQUE INDEX unfreeze_request_one_pending_idx ON public.unfreeze_request USING btree (principal_id)
    WHERE (status = 'PENDING'::text);

CREATE INDEX booking_series_idx ON public.booking USING btree (series_id) WHERE (series_id IS NOT NULL);

-- Sprint 3 (1.16.0): change requests and the lab's contact details (see migrations/007_change_requests_guidance_details_contact.sql).
CREATE TABLE public.site_contact (
    id uuid NOT NULL,
    email text DEFAULT ''::text NOT NULL,
    phone text DEFAULT ''::text NOT NULL,
    hours text DEFAULT ''::text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone,
    updated_by uuid
);
ALTER TABLE public.site_contact ADD CONSTRAINT site_contact_single_row_check
    CHECK ((id = '00000000-0000-0000-0000-000000000c01'::uuid));
ALTER TABLE ONLY public.site_contact ADD CONSTRAINT site_contact_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.site_contact
    ADD CONSTRAINT site_contact_updated_by_fk FOREIGN KEY (updated_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_replaces_fk FOREIGN KEY (replaces_id) REFERENCES public.booking(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX booking_one_open_change_idx ON public.booking USING btree (replaces_id)
    WHERE ((replaces_id IS NOT NULL) AND (status = ANY (ARRAY['WAITING_QUALIFICATION'::text, 'PENDING_APPROVAL'::text, 'WAITLISTED'::text])));

-- Sprint 3 (2026-10-25): per-person notification category choices (see migrations/008_notification_preferences.sql).
CREATE TABLE public.notification_preference (
    id uuid NOT NULL,
    principal_id uuid NOT NULL,
    category text NOT NULL,
    enabled boolean DEFAULT true NOT NULL
);
ALTER TABLE public.notification_preference ADD CONSTRAINT notification_preference_category_check
    CHECK (category = ANY (ARRAY['bookings'::text, 'reminders'::text, 'induction'::text, 'account'::text, 'resources'::text]));
ALTER TABLE ONLY public.notification_preference ADD CONSTRAINT notification_preference_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.notification_preference
    ADD CONSTRAINT notification_preference_principal_fk FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX notification_preference_person_category_idx ON public.notification_preference USING btree (principal_id, category);


--
-- PostgreSQL database dump complete
--

\unrestrict RFnq4Lcuo0qu5mjdAilspMYGCvAqoclsEh9CVV7p0jEAIdzLaGy3BEEUunfwWD6


-- Sprint 3 (1.19.0): separate delivery choices and attributed announcements. Repeatable; run after 008.
ALTER TABLE public.notification_preference ADD COLUMN IF NOT EXISTS email_enabled boolean DEFAULT true NOT NULL;
-- Preserve each message's selected channels, including email-only notices that must never enter the bell.
ALTER TABLE public.notification ADD COLUMN IF NOT EXISTS in_app boolean DEFAULT true NOT NULL;
ALTER TABLE public.notification ADD COLUMN IF NOT EXISTS email boolean DEFAULT true NOT NULL;

CREATE TABLE IF NOT EXISTS public.announcement (
    id uuid PRIMARY KEY,
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 120),
    body text NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 1000),
    kind text NOT NULL CHECK (kind IN ('MANUAL', 'RESOURCE_STATUS')),
    resource_id uuid REFERENCES public.bookable_resource(id),
    created_by uuid NOT NULL REFERENCES public.app_users(id),
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone,
    removed_at timestamp with time zone,
    removed_by uuid REFERENCES public.app_users(id),
    updated_at timestamp with time zone,
    author_role text NOT NULL CHECK (author_role IN ('ADMIN', 'MANAGER')),
    expected_back timestamp with time zone,
    CONSTRAINT announcement_kind_resource_check CHECK (
        (kind = 'MANUAL' AND resource_id IS NULL AND expected_back IS NULL) OR
        (kind = 'RESOURCE_STATUS' AND resource_id IS NOT NULL AND expires_at IS NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS announcement_resource_status_idx ON public.announcement(resource_id)
    WHERE kind = 'RESOURCE_STATUS' AND removed_at IS NULL;
CREATE INDEX IF NOT EXISTS announcement_created_idx ON public.announcement(created_at DESC, id DESC);

-- Sprint 3 (1.20.0): clearing personal history never deletes or changes a shared booking.
CREATE TABLE IF NOT EXISTS public.booking_history_removal (
    principal_id uuid NOT NULL REFERENCES public.app_users(id),
    booking_id uuid NOT NULL REFERENCES public.booking(id),
    removed_at timestamp with time zone NOT NULL,
    PRIMARY KEY (principal_id, booking_id)
);
