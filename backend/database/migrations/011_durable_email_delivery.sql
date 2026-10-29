-- Durable SMTP outbox with retry and worker leases. Repeatable; run after 010.
CREATE TABLE IF NOT EXISTS public.email_delivery (
    notification_id uuid PRIMARY KEY REFERENCES public.notification(id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS email_delivery_due_idx
    ON public.email_delivery(next_attempt_at, lease_until, created_at)
    WHERE status IN ('PENDING', 'IN_PROGRESS', 'RETRY');
