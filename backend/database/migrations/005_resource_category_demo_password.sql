-- Booking page filters and the simpler demo staff password (2026-10-18). For a local database created before
-- this date; run once after 004.
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/005_resource_category_demo_password.sql
-- Safe to run again.
--
-- 1. bookable_resource.category: equipment type used by the booking page filter (rooms stay NULL). The demo
--    equipment gets made-up categories; values someone already set are kept.
-- 2. The two fake demo staff accounts (z9000001 Admin, z9000002 Manager) sign in with the password "123".
--    Only these two demo accounts change; real staff keep their own passwords.

ALTER TABLE public.bookable_resource ADD COLUMN IF NOT EXISTS category text;

ALTER TABLE public.bookable_resource DROP CONSTRAINT IF EXISTS bookable_resource_category_check;
ALTER TABLE ONLY public.bookable_resource
    ADD CONSTRAINT bookable_resource_category_check CHECK (((category IS NULL) OR ((char_length(category) >= 1) AND (char_length(category) <= 60))));

UPDATE public.bookable_resource SET category = 'Electronics testing'
    WHERE id IN ('00000000-0000-0000-0000-000000000204', '00000000-0000-0000-0000-000000000205', '00000000-0000-0000-0000-000000000206', '00000000-0000-0000-0000-000000000207', '00000000-0000-0000-0000-000000000208', '00000000-0000-0000-0000-000000000209', '00000000-0000-0000-0000-000000000210', '00000000-0000-0000-0000-000000000213', '00000000-0000-0000-0000-000000000220') AND category IS NULL;
UPDATE public.bookable_resource SET category = 'Fabrication'
    WHERE id IN ('00000000-0000-0000-0000-000000000214', '00000000-0000-0000-0000-000000000215') AND category IS NULL;
UPDATE public.bookable_resource SET category = 'Imaging'
    WHERE id IN ('00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000218') AND category IS NULL;
UPDATE public.bookable_resource SET category = 'Lab analysis'
    WHERE id IN ('00000000-0000-0000-0000-000000000216', '00000000-0000-0000-0000-000000000217') AND category IS NULL;
UPDATE public.bookable_resource SET category = 'Microscopy'
    WHERE id IN ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000203') AND category IS NULL;
UPDATE public.bookable_resource SET category = 'Soldering'
    WHERE id IN ('00000000-0000-0000-0000-000000000211', '00000000-0000-0000-0000-000000000212', '00000000-0000-0000-0000-000000000219') AND category IS NULL;

UPDATE public.staff_credential
    SET password_hash = 'pbkdf2_sha256$1000000$smartlabdemostaff2$zptccOYVBe7KY3Xftwge1EpinjQjfTL5RQuWZcJnvLE=', invite_code = NULL, updated_at = now()
    WHERE principal_id IN ('00000000-0000-0000-0000-000000000901', '00000000-0000-0000-0000-000000000902');
