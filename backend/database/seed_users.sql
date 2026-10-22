--
-- Demo accounts for local development. Same zIDs and ids as the in-memory demo (booking/runtime.py),
-- so the demo login, tests and docs work the same with either storage.
-- All names and zIDs are invented; never commit real student data.
--

INSERT INTO public.app_users (id, zid, display_name, role, university_email, active) VALUES
    ('00000000-0000-0000-0000-000000000501', 'z1000001', 'Qualified demo student', 'STUDENT', 'z1000001@ad.unsw.edu.au', true),
    ('00000000-0000-0000-0000-000000000502', 'z1000002', 'New demo student', 'STUDENT', 'z1000002@ad.unsw.edu.au', true),
    ('00000000-0000-0000-0000-000000000503', 'z1000003', 'New demo student3', 'STUDENT', 'z1000003@ad.unsw.edu.au', true),
    ('00000000-0000-0000-0000-000000000504', 'z1000004', 'New demo student4', 'STUDENT', 'z1000004@ad.unsw.edu.au', true),
    ('00000000-0000-0000-0000-000000000901', 'z9000001', 'Demo administrator', 'ADMIN', 'z9000001@ad.unsw.edu.au', true),
    ('00000000-0000-0000-0000-000000000902', 'z9000002', 'Demo manager', 'MANAGER', 'z9000002@ad.unsw.edu.au', true);

-- Demo staff sign in on the staff page with the demo password "123" (fake accounts only).
INSERT INTO public.staff_credential (principal_id, password_hash, invite_code, updated_at) VALUES
    ('00000000-0000-0000-0000-000000000901', 'pbkdf2_sha256$1000000$smartlabdemostaff2$zptccOYVBe7KY3Xftwge1EpinjQjfTL5RQuWZcJnvLE=', NULL, now()),
    ('00000000-0000-0000-0000-000000000902', 'pbkdf2_sha256$1000000$smartlabdemostaff2$zptccOYVBe7KY3Xftwge1EpinjQjfTL5RQuWZcJnvLE=', NULL, now());

-- z1000001 already has a verified general induction (valid for 120 days from import), so the booking
-- flow can be tried straight away. The others start with no induction.
INSERT INTO public.stored_file (id, original_name, content_type, size, owner_id, data) VALUES
    ('00000000-0000-0000-0000-000000000701', 'demo-induction.pdf', 'application/pdf',
     octet_length(convert_to(E'%PDF-1.4\nDemo seeded induction evidence\n%%EOF', 'UTF8')),
     '00000000-0000-0000-0000-000000000501',
     convert_to(E'%PDF-1.4\nDemo seeded induction evidence\n%%EOF', 'UTF8'));

INSERT INTO public.qualification_submission
    (id, student_id, requirement_id, title, notes, file_id, submitted_at, status, reviewed_by, reviewed_at, valid_until)
VALUES
    ('00000000-0000-0000-0000-000000000601', '00000000-0000-0000-0000-000000000501', '00000000-0000-0000-0000-000000000001',
     'Seeded demo induction', 'Development fixture', '00000000-0000-0000-0000-000000000701', now(), 'VERIFIED',
     '00000000-0000-0000-0000-000000000901', now(), now() + interval '120 days');
