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
