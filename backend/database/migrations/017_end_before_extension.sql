-- An approved extension used to count towards the weekly allowance, because extending overwrote the end.
-- Keep the end before the first approved extension, so the allowance can leave the extension out. Run after 016.
-- Safe to run again. Bookings extended before this script get the end from their BOOKING_EXTENDED audit records.

ALTER TABLE public.booking ADD COLUMN IF NOT EXISTS end_before_extension timestamp with time zone;

UPDATE public.booking AS b
SET end_before_extension = first_extension.old_end
FROM (
    -- An extension only moves the end later, so the earliest old_end is the end before the first one.
    -- (Two extensions can share the same audit time, so ordering by time is not enough.)
    SELECT entity_id, min((details->>'old_end')::timestamptz) AS old_end
    FROM public.audit_record
    WHERE action = 'BOOKING_EXTENDED' AND entity_type = 'booking' AND details ? 'old_end'
    GROUP BY entity_id
) AS first_extension
WHERE b.id::text = first_extension.entity_id
  AND b.end_before_extension IS NULL
  AND first_extension.old_end > b.start AND first_extension.old_end < b."end";

ALTER TABLE public.booking DROP CONSTRAINT IF EXISTS booking_end_before_extension_check;
ALTER TABLE public.booking ADD CONSTRAINT booking_end_before_extension_check
    CHECK (((end_before_extension IS NULL) OR ((end_before_extension > start) AND (end_before_extension < "end"))));
