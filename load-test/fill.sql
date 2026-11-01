-- Sprint 3: load test history data, see README.md. Temporary databases only.
-- Perf data (temporary DB): 500 extra students, ~5000 bookings, ~5000 notifications, ~10000 audit rows.
INSERT INTO public.app_users (zid, display_name, role, university_email)
SELECT 'z2' || lpad(g::text, 6, '0'), 'Perf student ' || g, 'STUDENT', 'z2' || lpad(g::text, 6, '0') || '@example.test'
FROM generate_series(1, 500) g;

-- Past: 4400 bookings over the last 180 days (mostly approved and checked in).
INSERT INTO public.booking (student_id, resource_id, start, "end", purpose, created_at, status, reason_code, attendance, updated_at)
SELECT s.id, r.id, t.start, t.start + interval '1 hour', 'perf history', t.start - interval '10 days',
       CASE WHEN g % 10 = 0 THEN 'CANCELLED' WHEN g % 17 = 0 THEN 'REJECTED' ELSE 'APPROVED' END, NULL,
       CASE WHEN g % 10 = 0 OR g % 17 = 0 THEN NULL WHEN g % 9 = 0 THEN 'NO_SHOW' ELSE 'CHECKED_IN' END,
       t.start
FROM generate_series(1, 4400) g
CROSS JOIN LATERAL (SELECT date_trunc('hour', now()) - (g % 180 + 1) * interval '1 day' + (g % 8) * interval '1 hour' AS start) t
CROSS JOIN LATERAL (SELECT id FROM public.app_users WHERE role = 'STUDENT' AND zid LIKE 'z2%' ORDER BY zid OFFSET (g % 500) LIMIT 1) s
CROSS JOIN LATERAL (SELECT id FROM public.bookable_resource ORDER BY id OFFSET (g % 22) LIMIT 1) r;

-- Future: 600 bookings 7-30 days ahead, 08:00-13:00 Sydney, approved or waiting for review (review due later).
INSERT INTO public.booking (student_id, resource_id, start, "end", purpose, created_at, status, reason_code, review_due_at, updated_at)
SELECT s.id, r.id, t.start, t.start + interval '1 hour', 'perf future', now() - interval '1 day',
       CASE WHEN g % 3 = 0 THEN 'PENDING_APPROVAL' ELSE 'APPROVED' END, NULL,
       CASE WHEN g % 3 = 0 THEN now() + interval '20 hours' END, now() - interval '1 day'
FROM generate_series(1, 600) g
CROSS JOIN LATERAL (SELECT (date_trunc('day', now() AT TIME ZONE 'Australia/Sydney') + (7 + g % 24) * interval '1 day'
                            + (8 + g % 5) * interval '1 hour') AT TIME ZONE 'Australia/Sydney' AS start) t
CROSS JOIN LATERAL (SELECT id FROM public.app_users WHERE role = 'STUDENT' AND zid LIKE 'z2%' ORDER BY zid OFFSET ((g * 7) % 500) LIMIT 1) s
CROSS JOIN LATERAL (SELECT id FROM public.bookable_resource ORDER BY id OFFSET (g % 22) LIMIT 1) r;

INSERT INTO public.notification (id, recipient_id, kind, title, body, created_at)
SELECT gen_random_uuid(), b.student_id, 'BOOKING_APPROVED', 'Booking approved', 'perf', b.created_at
FROM public.booking b WHERE b.purpose LIKE 'perf%';

INSERT INTO public.audit_record (id, actor_id, action, entity_type, entity_id, at, details)
SELECT gen_random_uuid(), 'SYSTEM', 'BOOKING_TIME_PROCESSED', 'booking', b.id::text, b.created_at, '{}'::jsonb
FROM public.booking b, generate_series(1, 2) WHERE b.purpose LIKE 'perf%';

ANALYZE;
SELECT (SELECT count(*) FROM public.booking) AS bookings, (SELECT count(*) FROM public.notification) AS notifications,
       (SELECT count(*) FROM public.audit_record) AS audit, (SELECT count(*) FROM public.app_users) AS users;
