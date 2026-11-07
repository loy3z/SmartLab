-- Remove the booking freeze (2026-11-07, client Week 8 meeting: make cancelling easy instead of penalising).
-- Run after 013 before starting the new backend. Safe to run again.
-- Deletes the unfreeze requests and each person's freeze date and missed-booking count. Missed bookings stay
-- recorded on each booking (booking.attendance = 'NO_SHOW') for the usage report. The deploy script backs up the
-- database first; keep that backup if the old freeze records may be needed.

DROP TABLE IF EXISTS public.unfreeze_request;

ALTER TABLE public.app_users DROP CONSTRAINT IF EXISTS app_users_no_show_count_check;
ALTER TABLE public.app_users DROP COLUMN IF EXISTS no_show_count;
ALTER TABLE public.app_users DROP COLUMN IF EXISTS frozen_until;
