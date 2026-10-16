-- Staff sign-in (2026-10-14). Admins and Managers sign in on the staff page with zID + password; students keep
-- university sign-in. For a local database created before this date; run once after 002.
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/003_staff_sign_in.sql
-- Safe to run again.

CREATE TABLE IF NOT EXISTS public.staff_credential (
    principal_id uuid NOT NULL,
    password_hash text,
    invite_code text,
    updated_at timestamp with time zone
);
ALTER TABLE public.staff_credential DROP CONSTRAINT IF EXISTS staff_credential_principal_fkey;
ALTER TABLE public.staff_credential DROP CONSTRAINT IF EXISTS staff_credential_pkey;
ALTER TABLE ONLY public.staff_credential
    ADD CONSTRAINT staff_credential_pkey PRIMARY KEY (principal_id);
ALTER TABLE ONLY public.staff_credential
    ADD CONSTRAINT staff_credential_principal_fkey FOREIGN KEY (principal_id) REFERENCES public.app_users(id) ON DELETE CASCADE;

-- Demo staff (fake accounts) get the demo password "smartlab-staff-demo", same as the in-memory demo.
INSERT INTO public.staff_credential (principal_id, password_hash, invite_code, updated_at)
SELECT id, 'pbkdf2_sha256$1000000$smartlabdemostaff1$VEZGh4DfYxawq0X9qmaNEO0lg4UNdhtLIxnXrS21Btw=', NULL, now()
FROM public.app_users
WHERE id IN ('00000000-0000-0000-0000-000000000901', '00000000-0000-0000-0000-000000000902')
ON CONFLICT (principal_id) DO NOTHING;

-- Any other existing Admin or Manager gets an invite code to activate their account on the staff page.
-- A Manager can see it in User Management (or issue a new one with "Reset access").
INSERT INTO public.staff_credential (principal_id, password_hash, invite_code, updated_at)
SELECT id, NULL, upper(substr(md5(random()::text || id::text), 1, 4) || '-' || substr(md5(id::text || random()::text), 1, 4)), now()
FROM public.app_users
WHERE role IN ('ADMIN', 'MANAGER')
ON CONFLICT (principal_id) DO NOTHING;
