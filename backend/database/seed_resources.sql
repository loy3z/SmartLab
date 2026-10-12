--
-- PostgreSQL database dump
--

\restrict aXqCJuHehqHNcmSci9NXRB4uyC2qhLb9Daru21Jy3pd3lsL5EyWMVFkxf9jFwjo

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: qualification_requirement; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.qualification_requirement (id, name, description) VALUES ('00000000-0000-0000-0000-000000000001', 'General laboratory induction', 'Demo requirement; replace with client-approved training rules.');
INSERT INTO public.qualification_requirement (id, name, description) VALUES ('00000000-0000-0000-0000-000000000002', 'Advanced laboratory training', 'Separate prerequisite for Lab Room 2 and its specialist devices.');


--
-- Data for Name: bookable_resource; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000101', 'Lab Room 1', 'ROOM', 'Demo laboratory', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000102', 'Lab Room 2', 'ROOM', 'Demo laboratory', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000002', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000201', 'Microscope 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000202', 'Camera 001', 'EQUIPMENT', 'Lab Room 2', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000002', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000203', 'Microscope 002', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000204', 'Oscilloscope 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000205', 'Oscilloscope 002', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000206', 'Signal Generator 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000207', 'Bench Power Supply 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000208', 'Bench Power Supply 002', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000209', 'Digital Multimeter 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000210', 'Digital Multimeter 002', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000211', 'Soldering Station 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000212', 'Soldering Station 002', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000213', 'Logic Analyser 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000214', '3D Printer 001', 'EQUIPMENT', 'Lab Room 2', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000002', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000215', 'Laser Cutter 001', 'EQUIPMENT', 'Lab Room 2', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000002', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000216', 'Spectrometer 001', 'EQUIPMENT', 'Lab Room 2', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000002', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000217', 'Centrifuge 001', 'EQUIPMENT', 'Lab Room 2', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000002', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000218', 'Thermal Camera 001', 'EQUIPMENT', 'Lab Room 2', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000002', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000219', 'Fume Extractor 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);
INSERT INTO public.bookable_resource (id, name, kind, location, description, active, required_qualification_id, slot_minutes, max_booking_minutes, opening_time, closing_time, timezone, pending_hold_minutes) VALUES ('00000000-0000-0000-0000-000000000220', 'Data Logger 001', 'EQUIPMENT', 'Lab Room 1', 'Single resource; demonstration data.', true, '00000000-0000-0000-0000-000000000001', 30, 480, '08:00:00', '20:00:00', 'Australia/Sydney', 1440);


--
-- PostgreSQL database dump complete
--

\unrestrict aXqCJuHehqHNcmSci9NXRB4uyC2qhLb9Daru21Jy3pd3lsL5EyWMVFkxf9jFwjo

