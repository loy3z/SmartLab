-- Week 5 client review (2026-10-14). For a local database created before this date; run once after 001.
--   psql ... --set=ON_ERROR_STOP=1 --single-transaction --file=database/migrations/002_week5_rules.sql
-- Safe to run again.

-- Induction prerequisites (Advanced needs a current General), stored as data so policy changes need no code change.
ALTER TABLE public.qualification_requirement
    ADD COLUMN IF NOT EXISTS prerequisite_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL;
ALTER TABLE public.qualification_requirement DROP CONSTRAINT IF EXISTS qualification_requirement_not_own_prerequisite;
ALTER TABLE public.qualification_requirement ADD CONSTRAINT qualification_requirement_not_own_prerequisite
    CHECK ((NOT (id = ANY (prerequisite_ids))));
UPDATE public.qualification_requirement SET prerequisite_ids = ARRAY['00000000-0000-0000-0000-000000000001'::uuid]
    WHERE id = '00000000-0000-0000-0000-000000000002' AND prerequisite_ids = '{}'::uuid[]
      AND EXISTS (SELECT 1 FROM public.qualification_requirement WHERE id = '00000000-0000-0000-0000-000000000001');

-- Equipment belongs to a room (shown together to students; a closed room does not stop its equipment).
ALTER TABLE public.bookable_resource ADD COLUMN IF NOT EXISTS room_id uuid;
ALTER TABLE public.bookable_resource DROP CONSTRAINT IF EXISTS bookable_resource_room_check;
ALTER TABLE public.bookable_resource ADD CONSTRAINT bookable_resource_room_check
    CHECK (((room_id IS NULL) OR (kind = 'EQUIPMENT'::text)));
ALTER TABLE public.bookable_resource DROP CONSTRAINT IF EXISTS bookable_resource_room_fkey;
ALTER TABLE public.bookable_resource ADD CONSTRAINT bookable_resource_room_fkey
    FOREIGN KEY (room_id) REFERENCES public.bookable_resource(id) ON DELETE RESTRICT;
UPDATE public.bookable_resource AS item SET room_id = room.id
    FROM public.bookable_resource AS room
    WHERE item.kind = 'EQUIPMENT' AND item.room_id IS NULL AND room.kind = 'ROOM' AND room.name = item.location;
