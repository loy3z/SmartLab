-- Sprint 3 (1.20.0): clearing personal history never deletes or changes a shared booking.
CREATE TABLE IF NOT EXISTS public.booking_history_removal (
    principal_id uuid NOT NULL REFERENCES public.app_users(id),
    booking_id uuid NOT NULL REFERENCES public.booking(id),
    removed_at timestamp with time zone NOT NULL,
    PRIMARY KEY (principal_id, booking_id)
);
