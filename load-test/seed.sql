-- Sprint 3: load test accounts, see README.md.
-- Stress-test accounts for the temporary smartlab-stress database only (stress-ec2.sh); never run on the live database.
-- 200 students with a verified general induction, 9 more Admins and 1 more Manager. Together with the demo
-- accounts from seed_users.sql that makes 10 Admins and 2 Managers. Staff reuse the demo staff password hash.
INSERT INTO public.app_users (zid, display_name, role, university_email)
SELECT 'z5' || lpad(g::text, 6, '0'), 'Stress student ' || g, 'STUDENT', 'z5' || lpad(g::text, 6, '0') || '@example.test'
FROM generate_series(1, 200) g;

INSERT INTO public.app_users (zid, display_name, role, university_email)
SELECT 'z91' || lpad(g::text, 5, '0'), 'Stress admin ' || g, 'ADMIN', 'z91' || lpad(g::text, 5, '0') || '@example.test'
FROM generate_series(1, 9) g;

INSERT INTO public.app_users (zid, display_name, role, university_email)
VALUES ('z9200001', 'Stress manager 1', 'MANAGER', 'z9200001@example.test');

INSERT INTO public.staff_credential (principal_id, password_hash, invite_code, updated_at)
SELECT u.id, demo.password_hash, NULL, now()
FROM public.app_users u
CROSS JOIN (SELECT password_hash FROM public.staff_credential
            WHERE principal_id = '00000000-0000-0000-0000-000000000901') demo
WHERE u.zid LIKE 'z91%' OR u.zid = 'z9200001';

-- One evidence file per student, as the upload page would store it.
INSERT INTO public.stored_file (id, original_name, content_type, size, owner_id, data)
SELECT gen_random_uuid(), 'stress-induction.pdf', 'application/pdf', 4, u.id, convert_to('%PDF', 'UTF8')
FROM public.app_users u WHERE u.zid LIKE 'z5%';

INSERT INTO public.qualification_submission
    (student_id, requirement_id, title, notes, file_id, submitted_at, status, reviewed_by, reviewed_at, valid_until)
SELECT f.owner_id, '00000000-0000-0000-0000-000000000001', 'Stress induction', '', f.id, now(), 'VERIFIED',
       '00000000-0000-0000-0000-000000000901', now(), now() + interval '120 days'
FROM public.stored_file f WHERE f.original_name = 'stress-induction.pdf';

ANALYZE;
SELECT role, count(*) FROM public.app_users GROUP BY role ORDER BY role;
