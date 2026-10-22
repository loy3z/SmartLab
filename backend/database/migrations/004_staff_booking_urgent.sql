-- Staff booking and urgent requests (client email, 2026-10-17). For a local database created before this date;
-- run once after 003.
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/004_staff_booking_urgent.sql
-- Safe to run again.
--
-- booking.student_id stays the person the booking is for; created_by records who created it (an Admin or Manager
-- may book on behalf of someone). urgent/urgent_reason mark a request inside the minimum advance window that only
-- a Manager may approve.

ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS created_by uuid;
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS urgent boolean DEFAULT false NOT NULL;
ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS urgent_reason text;

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_created_by_fk;
ALTER TABLE ONLY public.booking
    ADD CONSTRAINT booking_created_by_fk FOREIGN KEY (created_by) REFERENCES public.app_users(id) ON DELETE RESTRICT;

-- Existing bookings were all created by the person they are for.
UPDATE public.booking SET created_by = student_id WHERE created_by IS NULL;
