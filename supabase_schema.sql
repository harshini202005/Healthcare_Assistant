-- ============================================================
-- Healthcare MCP Server - Supabase Database Schema
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql/new
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. DOCTORS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    email TEXT UNIQUE,
    phone TEXT,
    qualifications TEXT[],
    years_experience INTEGER,
    bio TEXT,
    image_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for specialty lookups
CREATE INDEX IF NOT EXISTS idx_doctors_specialty ON doctors(specialty);
CREATE INDEX IF NOT EXISTS idx_doctors_active ON doctors(is_active);

-- ============================================================
-- 2. DOCTOR SCHEDULES TABLE (Weekly Recurring)
-- ============================================================
CREATE TABLE IF NOT EXISTS doctor_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id TEXT REFERENCES doctors(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6), -- 0=Monday, 6=Sunday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doctor_id, day_of_week)
);

-- Index for schedule lookups
CREATE INDEX IF NOT EXISTS idx_schedules_doctor ON doctor_schedules(doctor_id);
CREATE INDEX IF NOT EXISTS idx_schedules_day ON doctor_schedules(day_of_week);

-- ============================================================
-- 3. DOCTOR AVAILABILITY OVERRIDES (Vacations, Extra Slots)
-- ============================================================
CREATE TABLE IF NOT EXISTS doctor_availability (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id TEXT REFERENCES doctors(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,
    reason TEXT, -- e.g., "On vacation", "Extra clinic hours"
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doctor_id, date)
);

-- Index for availability lookups
CREATE INDEX IF NOT EXISTS idx_availability_doctor ON doctor_availability(doctor_id);
CREATE INDEX IF NOT EXISTS idx_availability_date ON doctor_availability(date);

-- ============================================================
-- 4. APPOINTMENTS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    confirmation_number TEXT UNIQUE NOT NULL,
    patient_id TEXT NOT NULL,
    doctor_id TEXT REFERENCES doctors(id) ON DELETE SET NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    specialty TEXT NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'completed', 'cancelled', 'no_show')),
    notes TEXT,
    booked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for appointment queries
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_datetime ON appointments(appointment_date, appointment_time);

-- ============================================================
-- 5. PATIENTS TABLE (linked 1:1 with Supabase Auth users)
-- ============================================================
CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    phone TEXT,
    date_of_birth DATE,
    allergies TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patients_email ON patients(email);

DROP TRIGGER IF EXISTS update_patients_updated_at ON patients;
CREATE TRIGGER update_patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- ROW LEVEL SECURITY POLICIES
-- ============================================================
-- NOTE: The FastAPI backend talks to Supabase using the service_role key,
-- which bypasses RLS entirely. Real authorization is enforced in the API
-- layer (backend/auth.py + backend/main.py) by verifying each request's
-- Supabase Auth JWT and scoping queries to that patient's own id. These
-- policies exist as defense-in-depth in case the anon key is ever used
-- directly (e.g. a future client-side integration).

-- Enable RLS on all tables
ALTER TABLE doctors ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctor_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE doctor_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read access to doctors and schedules
DROP POLICY IF EXISTS "Allow public read doctors" ON doctors;
CREATE POLICY "Allow public read doctors" ON doctors
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow public read schedules" ON doctor_schedules;
CREATE POLICY "Allow public read schedules" ON doctor_schedules
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow public read availability" ON doctor_availability;
CREATE POLICY "Allow public read availability" ON doctor_availability
    FOR SELECT USING (true);

-- Appointments are scoped to the owning patient (auth.uid())
DROP POLICY IF EXISTS "Allow public insert appointments" ON appointments;
DROP POLICY IF EXISTS "Allow public select appointments" ON appointments;
DROP POLICY IF EXISTS "Allow public update appointments" ON appointments;
DROP POLICY IF EXISTS "Patients can insert own appointments" ON appointments;
DROP POLICY IF EXISTS "Patients can view own appointments" ON appointments;
DROP POLICY IF EXISTS "Patients can update own appointments" ON appointments;

CREATE POLICY "Patients can insert own appointments" ON appointments
    FOR INSERT WITH CHECK (patient_id = auth.uid()::text);

CREATE POLICY "Patients can view own appointments" ON appointments
    FOR SELECT USING (patient_id = auth.uid()::text);

CREATE POLICY "Patients can update own appointments" ON appointments
    FOR UPDATE USING (patient_id = auth.uid()::text);

-- Patients can only see/edit their own profile
DROP POLICY IF EXISTS "Patients can view own profile" ON patients;
DROP POLICY IF EXISTS "Patients can insert own profile" ON patients;
DROP POLICY IF EXISTS "Patients can update own profile" ON patients;

CREATE POLICY "Patients can view own profile" ON patients
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Patients can insert own profile" ON patients
    FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Patients can update own profile" ON patients
    FOR UPDATE USING (auth.uid() = id);

-- ============================================================
-- TRIGGER: Update updated_at timestamp
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_doctors_updated_at ON doctors;
CREATE TRIGGER update_doctors_updated_at
    BEFORE UPDATE ON doctors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_appointments_updated_at ON appointments;
CREATE TRIGGER update_appointments_updated_at
    BEFORE UPDATE ON appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 6. DOCTOR LOGIN (links a doctors row to a Supabase Auth user)
-- ============================================================
-- Doctors are provisioned (not self-signup) — see seed_database.py, which
-- creates a confirmed Auth account per doctor and links it here.
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_doctors_auth_user ON doctors(auth_user_id);

-- Doctors can see/update only their own appointments (defense-in-depth; the
-- backend uses the service_role key and enforces this in the API layer
-- regardless — see backend/auth.py::get_current_doctor).
DROP POLICY IF EXISTS "Doctors can view own appointments" ON appointments;
CREATE POLICY "Doctors can view own appointments" ON appointments
    FOR SELECT USING (doctor_id IN (SELECT id FROM doctors WHERE auth_user_id = auth.uid()));

DROP POLICY IF EXISTS "Doctors can update own appointments" ON appointments;
CREATE POLICY "Doctors can update own appointments" ON appointments
    FOR UPDATE USING (doctor_id IN (SELECT id FROM doctors WHERE auth_user_id = auth.uid()));

-- ============================================================
-- 7. DOCTOR DASHBOARD EXTENSIONS
-- ============================================================
-- Everything below is additive — safe to re-run, does not touch existing rows.

-- 7a. Extra profile fields for the Doctor Profile page
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS hospital TEXT;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS consultation_fee NUMERIC(10, 2);

-- 7b. Appointment lifecycle: bookings are auto-confirmed (no doctor approval
-- step) — 'pending'/'rejected' are kept as available statuses for manual use
-- from the dashboard (e.g. a doctor flagging a booking for review), but
-- booking() always creates appointments as 'confirmed' directly.
ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_status_check;
ALTER TABLE appointments ADD CONSTRAINT appointments_status_check
    CHECK (status IN ('pending', 'confirmed', 'completed', 'cancelled', 'rejected', 'no_show'));
ALTER TABLE appointments ALTER COLUMN status SET DEFAULT 'confirmed';

-- 7c. Doctor notifications — always written with the doctor_id that owns the
-- appointment (see backend/tools/booking.py), so a doctor only ever sees
-- notifications generated by their own patients' activity.
--
-- NOTE: named doctor_notifications, NOT notifications — this Supabase project
-- already has an unrelated pre-existing `notifications` table (patient_id +
-- workflow_run_id + generic type/metadata, used by a separate
-- workflows/workflow_runs/knowledge_chunks system that also lives in this
-- project). Do not rename or touch that table; this is a distinct one.
CREATE TABLE IF NOT EXISTS doctor_notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id TEXT REFERENCES doctors(id) ON DELETE CASCADE,
    appointment_id UUID REFERENCES appointments(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN (
        'new_appointment', 'appointment_accepted', 'appointment_cancelled',
        'appointment_rescheduled', 'appointment_reminder'
    )),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doctor_notifications_doctor ON doctor_notifications(doctor_id);
CREATE INDEX IF NOT EXISTS idx_doctor_notifications_doctor_unread ON doctor_notifications(doctor_id, is_read);
CREATE INDEX IF NOT EXISTS idx_doctor_notifications_appointment ON doctor_notifications(appointment_id);

ALTER TABLE doctor_notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Doctors can view own notifications" ON doctor_notifications;
CREATE POLICY "Doctors can view own notifications" ON doctor_notifications
    FOR SELECT USING (doctor_id IN (SELECT id FROM doctors WHERE auth_user_id = auth.uid()));
DROP POLICY IF EXISTS "Doctors can update own notifications" ON doctor_notifications;
CREATE POLICY "Doctors can update own notifications" ON doctor_notifications
    FOR UPDATE USING (doctor_id IN (SELECT id FROM doctors WHERE auth_user_id = auth.uid()));

-- 7d. Doctor notes — private per doctor+patient. Never joined/exposed across
-- doctor_id boundaries by the API layer (see backend/main.py doctor endpoints).
CREATE TABLE IF NOT EXISTS doctor_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id TEXT REFERENCES doctors(id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL,
    appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doctor_notes_doctor_patient ON doctor_notes(doctor_id, patient_id);

ALTER TABLE doctor_notes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Doctors can manage own notes" ON doctor_notes;
CREATE POLICY "Doctors can manage own notes" ON doctor_notes
    FOR ALL USING (doctor_id IN (SELECT id FROM doctors WHERE auth_user_id = auth.uid()));

-- 7e. Diet plans — persisted output of the existing AI Diet Generator tool
-- (generate_diet), tied to the patient who was signed in when they asked for
-- one. Doctors can view a patient's plans (read-only) once that patient has
-- an appointment with them; the backend enforces this the same way it scopes
-- everything else — see get_patient_detail_for_doctor.
CREATE TABLE IF NOT EXISTS diet_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id TEXT NOT NULL,
    preferences TEXT,
    daily_calories INTEGER,
    allergies TEXT[],
    plan_text TEXT,
    meals JSONB,
    source TEXT, -- 'mistral_ai' | 'template'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diet_plans_patient ON diet_plans(patient_id);

ALTER TABLE diet_plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Patients can view own diet plans" ON diet_plans;
CREATE POLICY "Patients can view own diet plans" ON diet_plans
    FOR SELECT USING (patient_id = auth.uid()::text);
DROP POLICY IF EXISTS "Patients can insert own diet plans" ON diet_plans;
CREATE POLICY "Patients can insert own diet plans" ON diet_plans
    FOR INSERT WITH CHECK (patient_id = auth.uid()::text);
DROP POLICY IF EXISTS "Doctors can view their patients' diet plans" ON diet_plans;
CREATE POLICY "Doctors can view their patients' diet plans" ON diet_plans
    FOR SELECT USING (
        patient_id IN (
            SELECT patient_id FROM appointments
            WHERE doctor_id IN (SELECT id FROM doctors WHERE auth_user_id = auth.uid())
        )
    );

-- 7f. Health queries — persisted history of the existing AI health-assistant
-- tool (general_query), same patient/doctor visibility rules as diet_plans.
-- Clearly AI-generated, not a diagnosis — see backend/main.py + dashboard UI.
CREATE TABLE IF NOT EXISTS health_queries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    source TEXT, -- 'mistral_ai' | 'template'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_queries_patient ON health_queries(patient_id);

ALTER TABLE health_queries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Patients can view own health queries" ON health_queries;
CREATE POLICY "Patients can view own health queries" ON health_queries
    FOR SELECT USING (patient_id = auth.uid()::text);
DROP POLICY IF EXISTS "Patients can insert own health queries" ON health_queries;
CREATE POLICY "Patients can insert own health queries" ON health_queries
    FOR INSERT WITH CHECK (patient_id = auth.uid()::text);
DROP POLICY IF EXISTS "Doctors can view their patients' health queries" ON health_queries;
CREATE POLICY "Doctors can view their patients' health queries" ON health_queries
    FOR SELECT USING (
        patient_id IN (
            SELECT patient_id FROM appointments
            WHERE doctor_id IN (SELECT id FROM doctors WHERE auth_user_id = auth.uid())
        )
    );