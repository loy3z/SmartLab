-- Manager-only internal information about rooms and equipment (2026-11-07, client Week 8 meeting): owner, UNSW asset
-- number, where it came from, specifications. Its own table so it never travels with the public resource data.
-- Run after 014. Safe to run again; adds a table only, existing data is unchanged.

CREATE TABLE IF NOT EXISTS public.resource_internal_info (
    resource_id uuid NOT NULL,
    owner text DEFAULT ''::text NOT NULL,
    asset_number text DEFAULT ''::text NOT NULL,
    provided_by text DEFAULT ''::text NOT NULL,
    specifications text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone,
    updated_by uuid
);
ALTER TABLE public.resource_internal_info DROP CONSTRAINT IF EXISTS resource_internal_info_pkey;
ALTER TABLE ONLY public.resource_internal_info ADD CONSTRAINT resource_internal_info_pkey PRIMARY KEY (resource_id);
ALTER TABLE public.resource_internal_info DROP CONSTRAINT IF EXISTS resource_internal_info_resource_fk;
ALTER TABLE ONLY public.resource_internal_info
    ADD CONSTRAINT resource_internal_info_resource_fk FOREIGN KEY (resource_id) REFERENCES public.bookable_resource(id) ON DELETE CASCADE;
ALTER TABLE public.resource_internal_info DROP CONSTRAINT IF EXISTS resource_internal_info_updated_by_fk;
ALTER TABLE ONLY public.resource_internal_info
    ADD CONSTRAINT resource_internal_info_updated_by_fk FOREIGN KEY (updated_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;
ALTER TABLE public.resource_internal_info DROP CONSTRAINT IF EXISTS resource_internal_info_length_check;
ALTER TABLE public.resource_internal_info ADD CONSTRAINT resource_internal_info_length_check
    CHECK (((char_length(owner) <= 120) AND (char_length(asset_number) <= 60) AND (char_length(provided_by) <= 120)
            AND (char_length(specifications) <= 2000)));
