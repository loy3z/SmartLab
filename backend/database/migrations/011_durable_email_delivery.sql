-- Durable SMTP outbox with retry and worker leases. Repeatable; run after 010.
CREATE TABLE IF NOT EXISTS public.email_delivery (
    notification_id uuid PRIMARY KEY CONSTRAINT email_delivery_notification_fk REFERENCES public.notification(id) ON DELETE CASCADE,
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
    CONSTRAINT email_delivery_status_check CHECK (status IN ('PENDING', 'IN_PROGRESS', 'RETRY', 'SENT', 'FAILED')),
    CONSTRAINT email_delivery_state_check CHECK (
        (status = 'PENDING' AND next_attempt_at IS NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NULL) OR
        (status = 'IN_PROGRESS' AND lease_until IS NOT NULL AND worker_id IS NOT NULL AND sent_at IS NULL) OR
        (status = 'RETRY' AND next_attempt_at IS NOT NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NULL) OR
        (status = 'SENT' AND next_attempt_at IS NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NOT NULL) OR
        (status = 'FAILED' AND next_attempt_at IS NULL AND lease_until IS NULL AND worker_id IS NULL AND sent_at IS NULL)
    )
);

-- Sprint 3 (2026-11-01): original 011 used PostgreSQL's automatic FK name. CREATE TABLE IF NOT EXISTS
-- leaves that table untouched, so normalize existing installations too, without dropping the FK or any rows.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.email_delivery'::regclass
               AND conname = 'email_delivery_notification_id_fkey' AND contype = 'f')
       AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.email_delivery'::regclass
                       AND conname = 'email_delivery_notification_fk') THEN
        ALTER TABLE public.email_delivery RENAME CONSTRAINT email_delivery_notification_id_fkey
            TO email_delivery_notification_fk;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS email_delivery_due_idx
    ON public.email_delivery(next_attempt_at, lease_until, created_at)
    WHERE status IN ('PENDING', 'IN_PROGRESS', 'RETRY');
