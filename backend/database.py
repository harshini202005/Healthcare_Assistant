"""
Database layer for Healthcare MCP Server
Uses Supabase (PostgreSQL) for storing doctors, schedules, and appointments
"""

import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Doctor Dashboard demo doctors (see README / task spec). Pulled out as a
# module-level constant — rather than inline in Database.seed_doctors() —
# so other code (e.g. seed_database.py's demo appointment/history seeding)
# can reference these doctors by id/email without duplicating the data.
DEMO_DOCTORS = [
    {
        "id": "doc_101", "name": "Dr. Priya", "specialty": "dermatology",
        "email": "priya.derm@healthcare-demo.com", "phone": "+91 90000 10101",
        "years_experience": 11, "qualifications": ["MBBS", "MD Dermatology"],
        "bio": "Specializes in skin, hair, and nail conditions with a focus on acne, eczema, and cosmetic dermatology.",
        "hospital": "Sunrise Skin & Wellness Clinic", "consultation_fee": 800.00,
        "image_url": "https://api.dicebear.com/7.x/initials/svg?seed=Priya&backgroundColor=f8bbd0",
    },
    {
        "id": "doc_102", "name": "Dr. Rahul", "specialty": "cardiology",
        "email": "rahul.cardio@healthcare-demo.com", "phone": "+91 90000 10102",
        "years_experience": 16, "qualifications": ["MBBS", "MD", "DM Cardiology"],
        "bio": "Interventional cardiologist focused on preventive heart care, hypertension, and post-cardiac-event follow-up.",
        "hospital": "City Heart Institute", "consultation_fee": 1200.00,
        "image_url": "https://api.dicebear.com/7.x/initials/svg?seed=Rahul&backgroundColor=bbdefb",
    },
    {
        "id": "doc_103", "name": "Dr. Ananya", "specialty": "nutrition",
        "email": "ananya.nutrition@healthcare-demo.com", "phone": "+91 90000 10103",
        "years_experience": 9, "qualifications": ["MSc Clinical Nutrition", "RD"],
        "bio": "Registered dietitian helping patients with weight management, diabetic diets, and sports nutrition.",
        "hospital": "Wellness Nutrition Center", "consultation_fee": 600.00,
        "image_url": "https://api.dicebear.com/7.x/initials/svg?seed=Ananya&backgroundColor=c8e6c9",
    },
]

class Database:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        """Initialize Supabase client"""
        supabase_url = os.getenv("SUPABASE_URL")
        
        # Use service_role key for admin operations if available, otherwise anon key
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_KEY) must be set in environment. "
                "Get them from https://supabase.com/dashboard/project/_/settings/api"
            )
        
        self.client: Client = create_client(supabase_url, supabase_key)
    
    # ============ Doctor Operations ============
    
    def get_doctors(self, specialty: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all doctors or filter by specialty"""
        query = self.client.table("doctors").select("*")
        
        if specialty:
            query = query.eq("specialty", specialty.lower())
        
        response = query.execute()
        return response.data if response.data else []
    
    def get_doctor_by_id(self, doctor_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific doctor by ID. Returns None if not found (or invalid ID) instead of raising."""
        try:
            response = self.client.table("doctors").select("*").eq("id", doctor_id).single().execute()
            return response.data if hasattr(response, 'data') else None
        except Exception:
            # .single() raises when zero (or more than one) rows match — e.g. an
            # unresolved doctor name reaching here as a raw, non-"doc_XXX" ID.
            return None
    
    def get_doctor_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a doctor by name (partial match)"""
        # Remove common prefixes and normalize
        normalized_name = name.lower().replace('dr.', '').replace('dr ', '').strip()
        
        # Try exact match first
        response = self.client.table("doctors").select("*").ilike("name", f"%{normalized_name}%").execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        # Try with "Dr. " prefix
        if not normalized_name.startswith('dr'):
            response = self.client.table("doctors").select("*").ilike("name", f"%Dr. {normalized_name}%").execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
        
        return None
    
    def search_doctors(self, search_term: str) -> List[Dict[str, Any]]:
        """Search doctors by name, specialty, or ID"""
        results = []
        
        # Try ID match
        if search_term.startswith('doc_'):
            doctor = self.get_doctor_by_id(search_term)
            if doctor:
                results.append(doctor)
                return results
        
        # Try name match
        normalized = search_term.lower().replace('dr.', '').replace('dr ', '').strip()
        response = self.client.table("doctors").select("*").ilike("name", f"%{normalized}%").execute()
        if response.data:
            results.extend(response.data)
        
        # Try specialty match
        if not results:
            response = self.client.table("doctors").select("*").ilike("specialty", f"%{normalized}%").execute()
            if response.data:
                results.extend(response.data)
        
        return results
    
    def seed_doctors(self):
        """Seed initial doctor data (run once) - requires service_role key"""
        doctors = [
            {"id": "doc_001", "name": "Dr. Sarah Johnson", "specialty": "cardiology", "email": "sarah.j@healthcare.com", "years_experience": 12},
            {"id": "doc_002", "name": "Dr. Michael Chen", "specialty": "cardiology", "email": "michael.c@healthcare.com", "years_experience": 8},
            {"id": "doc_003", "name": "Dr. Emily Davis", "specialty": "dermatology", "email": "emily.d@healthcare.com", "years_experience": 15},
            {"id": "doc_004", "name": "Dr. James Wilson", "specialty": "orthopedics", "email": "james.w@healthcare.com", "years_experience": 10},
            {"id": "doc_005", "name": "Dr. Priya Patel", "specialty": "pediatrics", "email": "priya.p@healthcare.com", "years_experience": 7},
            {"id": "doc_006", "name": "Dr. Robert Brown", "specialty": "general practice", "email": "robert.b@healthcare.com", "years_experience": 20},
            {"id": "doc_007", "name": "Dr. Lisa Anderson", "specialty": "neurology", "email": "lisa.a@healthcare.com", "years_experience": 14},
            {"id": "doc_008", "name": "Dr. David Kim", "specialty": "general practice", "email": "david.k@healthcare.com", "years_experience": 9},
        ] + DEMO_DOCTORS

        seeded = 0
        for doctor in doctors:
            try:
                self.client.table("doctors").upsert(doctor).execute()
                seeded += 1
            except Exception as e:
                print(f"   ⚠️  {doctor['name']}: {str(e)[:60]}")
        
        return seeded

    def get_doctor_by_auth_user_id(self, auth_user_id: str) -> Optional[Dict[str, Any]]:
        """Get a doctor's row by their linked Supabase Auth user id (used by doctor login)."""
        response = self.client.table("doctors").select("*").eq("auth_user_id", auth_user_id).maybe_single().execute()
        return response.data if response else None

    def set_doctor_auth_user(self, doctor_id: str, auth_user_id: str) -> Dict[str, Any]:
        """Link a doctor row to a Supabase Auth user id (run once by seed_database.py)."""
        response = self.client.table("doctors").update({"auth_user_id": auth_user_id}).eq("id", doctor_id).execute()
        return response.data[0] if response.data else {}

    def update_doctor_profile(self, doctor_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update editable profile/availability-summary fields on a doctor's own row."""
        if not fields:
            return self.get_doctor_by_id(doctor_id)
        response = self.client.table("doctors").update(fields).eq("id", doctor_id).execute()
        return response.data[0] if response.data else None

    # ============ Patient Operations ============

    def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get a patient profile by their Supabase Auth user id"""
        response = self.client.table("patients").select("*").eq("id", patient_id).maybe_single().execute()
        return response.data if response else None

    def upsert_patient(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a patient profile (patient_data must include 'id')"""
        response = self.client.table("patients").upsert(patient_data).execute()
        return response.data[0] if response.data else patient_data

    def get_appointments_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """Get all appointments for a patient, most recent first, with doctor info joined"""
        response = self.client.table("appointments") \
            .select("*, doctors(name, specialty)") \
            .eq("patient_id", patient_id) \
            .order("appointment_date", desc=True) \
            .order("appointment_time", desc=True) \
            .execute()
        return response.data if response.data else []

    def get_appointment_by_confirmation(self, confirmation_number: str) -> Optional[Dict[str, Any]]:
        """Get a single appointment by confirmation number (no join)"""
        response = self.client.table("appointments") \
            .select("*") \
            .eq("confirmation_number", confirmation_number) \
            .maybe_single().execute()
        return response.data if response else None

    # ============ Schedule Operations ============
    
    def get_doctor_schedule(self, doctor_id: str) -> List[Dict[str, Any]]:
        """Get weekly schedule for a doctor"""
        response = self.client.table("doctor_schedules") \
            .select("*") \
            .eq("doctor_id", doctor_id) \
            .order("day_of_week") \
            .execute()
        return response.data if response.data else []
    
    def get_default_schedules(self) -> List[Dict[str, Any]]:
        """Get default schedules for seeding"""
        schedules = []
        default_times = [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},  # Monday
            {"day_of_week": 1, "start_time": "09:00", "end_time": "17:00"},  # Tuesday
            {"day_of_week": 2, "start_time": "09:00", "end_time": "17:00"},  # Wednesday
            {"day_of_week": 3, "start_time": "09:00", "end_time": "17:00"},  # Thursday
            {"day_of_week": 4, "start_time": "09:00", "end_time": "17:00"},  # Friday
        ]
        
        doctor_ids = [
            "doc_001", "doc_002", "doc_003", "doc_004", "doc_005", "doc_006", "doc_007", "doc_008",
            "doc_101", "doc_102", "doc_103",
        ]
        
        for doctor_id in doctor_ids:
            for schedule in default_times:
                schedules.append({
                    "doctor_id": doctor_id,
                    "day_of_week": schedule["day_of_week"],
                    "start_time": schedule["start_time"],
                    "end_time": schedule["end_time"],
                    "is_available": True
                })
        
        return schedules
    
    def seed_schedules(self):
        """Seed default schedules for all doctors - requires service_role key"""
        schedules = self.get_default_schedules()

        seeded = 0
        for schedule in schedules:
            try:
                # on_conflict must name the actual (doctor_id, day_of_week) unique
                # constraint — without it, upsert() only knows how to resolve
                # conflicts on the primary key (id), which never collides since a
                # fresh id is generated each call. That made every re-run of this
                # function report "duplicate key" errors on rows that already
                # existed (the insert doesn't actually go through, unlike it may
                # look from the error text) instead of updating them.
                self.client.table("doctor_schedules").upsert(schedule, on_conflict="doctor_id,day_of_week").execute()
                seeded += 1
            except Exception as e:
                error_msg = str(e)
                if "violates row-level security" in error_msg:
                    pass  # Silently skip RLS errors
                else:
                    print(f"   ⚠️  Schedule error: {error_msg[:60]}")
        
        return seeded
    
    # ============ Appointment Operations ============
    
    def get_appointments(self, doctor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get appointments, optionally filtered by doctor and/or date"""
        query = self.client.table("appointments").select("*")
        
        if doctor_id:
            query = query.eq("doctor_id", doctor_id)
        if date:
            query = query.eq("appointment_date", date)
        
        response = query.order("appointment_time").execute()
        return response.data if response.data else []
    
    def check_doctor_conflict(self, doctor_id: str, date: str, time: str) -> Optional[Dict[str, Any]]:
        """Check if doctor already has an appointment at this time"""
        try:
            response = self.client.table("appointments") \
                .select("*") \
                .eq("doctor_id", doctor_id) \
                .eq("appointment_date", date) \
                .eq("appointment_time", time) \
                .neq("status", "cancelled") \
                .limit(1) \
                .execute()
            
            if response and response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            # If any error (including no rows found), return None (no conflict)
            return None
    
    def create_appointment(self, appointment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new appointment"""
        response = self.client.table("appointments").insert(appointment_data).execute()
        return response.data[0] if response.data else appointment_data

    def get_doctor_appointments(self, doctor_id: str, date: str) -> List[Dict[str, Any]]:
        """
        Get every non-cancelled appointment for one doctor on one date, in a single
        query — used to build the occupied-slots/queue view without re-querying
        per candidate time slot.
        """
        try:
            response = self.client.table("appointments") \
                .select("*") \
                .eq("doctor_id", doctor_id) \
                .eq("appointment_date", date) \
                .neq("status", "cancelled") \
                .order("appointment_time") \
                .execute()
            return response.data if response.data else []
        except Exception:
            return []

    def get_appointments_by_doctor(
        self,
        doctor_id: str,
        date: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get a doctor's own appointments (all statuses, unlike get_doctor_appointments
        above which excludes cancelled for slot-availability purposes) — used by the
        doctor dashboard, optionally scoped to one date, a date range, and/or a status.
        """
        query = self.client.table("appointments").select("*").eq("doctor_id", doctor_id)
        if date:
            query = query.eq("appointment_date", date)
        if date_from:
            query = query.gte("appointment_date", date_from)
        if date_to:
            query = query.lte("appointment_date", date_to)
        if status:
            query = query.eq("status", status)
        response = query.order("appointment_date").order("appointment_time").execute()
        return response.data if response.data else []

    def doctor_has_patient(self, doctor_id: str, patient_id: str) -> bool:
        """Whether this patient has ever had an appointment with this doctor — the
        gate that stops a doctor from reading an unrelated patient's details/notes."""
        response = self.client.table("appointments") \
            .select("id") \
            .eq("doctor_id", doctor_id) \
            .eq("patient_id", patient_id) \
            .limit(1) \
            .execute()
        return bool(response.data)

    def get_dashboard_summary(self, doctor_id: str) -> Dict[str, Any]:
        """
        Compute the doctor dashboard's summary cards + overview lists from a single
        fetch of this doctor's appointments (cheap at demo/small-clinic scale, and
        keeps every count trivially consistent with every list on the same page).
        """
        appts = self.get_appointments_by_doctor(doctor_id)
        today = datetime.now().date().isoformat()

        total_patients = len({a["patient_id"] for a in appts})
        today_appts = [a for a in appts if a["appointment_date"] == today]
        upcoming_appts = [
            a for a in appts
            if a["appointment_date"] > today and a["status"] in ("pending", "confirmed")
        ]
        completed_appts = [a for a in appts if a["status"] == "completed"]
        pending_appts = [a for a in appts if a["status"] == "pending"]

        patient_ids = [a["patient_id"] for a in appts]
        patients = self.get_patients_by_ids(patient_ids)

        def enrich(a: Dict[str, Any]) -> Dict[str, Any]:
            p = patients.get(a["patient_id"], {})
            return {**a, "patient_name": p.get("full_name") or p.get("email") or "Unknown patient"}

        by_booked_desc = sorted(appts, key=lambda a: a.get("booked_at") or "", reverse=True)
        week_ahead = (datetime.now().date() + timedelta(days=7)).isoformat()
        upcoming_week = sorted(
            (a for a in upcoming_appts if a["appointment_date"] <= week_ahead),
            key=lambda a: (a["appointment_date"], a["appointment_time"]),
        )

        return {
            "total_patients": total_patients,
            "today_count": len(today_appts),
            "upcoming_count": len(upcoming_appts),
            "completed_count": len(completed_appts),
            "pending_count": len(pending_appts),
            "todays_schedule": [enrich(a) for a in sorted(today_appts, key=lambda a: a["appointment_time"])],
            # Bookings are auto-confirmed (no approval step — see booking.book()),
            # so this is "what's coming up" rather than a queue needing action.
            "upcoming_this_week": [enrich(a) for a in upcoming_week][:5],
            "recent_patients": [enrich(a) for a in by_booked_desc[:5]],
        }

    # ============ Patients (from a doctor's perspective) ============

    def get_patients_for_doctor(
        self, doctor_id: str, search: Optional[str] = None, filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Build the doctor's "My Patients" list: every patient who has ever booked
        with this doctor, aggregated with appointment stats. appointments has no FK
        to patients, so this is fetch-appointments-then-merge (same pattern as
        get_patients_by_ids).
        """
        appts = self.get_appointments_by_doctor(doctor_id)
        if not appts:
            return []

        today = datetime.now().date().isoformat()
        by_patient: Dict[str, List[Dict[str, Any]]] = {}
        for a in appts:
            by_patient.setdefault(a["patient_id"], []).append(a)

        profiles = self.get_patients_by_ids(list(by_patient.keys()))

        results = []
        for patient_id, patient_appts in by_patient.items():
            patient_appts.sort(key=lambda a: (a["appointment_date"], a["appointment_time"]))
            past = [a for a in patient_appts if a["appointment_date"] < today]
            future = [a for a in patient_appts if a["appointment_date"] >= today and a["status"] in ("pending", "confirmed")]
            profile = profiles.get(patient_id, {})

            entry = {
                "patient_id": patient_id,
                "name": profile.get("full_name") or profile.get("email") or "Unknown patient",
                "email": profile.get("email"),
                "phone": profile.get("phone"),
                "date_of_birth": profile.get("date_of_birth"),
                "appointment_count": len(patient_appts),
                "last_appointment": past[-1]["appointment_date"] if past else None,
                "next_appointment": future[0]["appointment_date"] if future else None,
                "is_new": len(patient_appts) == 1,
                "status": patient_appts[-1]["status"],
            }
            results.append(entry)

        if search:
            term = search.lower()
            results = [
                r for r in results
                if term in (r["name"] or "").lower()
                or term in (r["email"] or "").lower()
                or term in (r["phone"] or "").lower()
            ]

        if filter == "new":
            results = [r for r in results if r["is_new"]]
        elif filter == "returning":
            results = [r for r in results if not r["is_new"]]
        elif filter == "upcoming":
            results = [r for r in results if r["next_appointment"]]
        elif filter == "recent":
            results = [r for r in results if r["last_appointment"]]

        results.sort(key=lambda r: r["name"] or "")
        return results

    def get_patient_detail_for_doctor(self, doctor_id: str, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Full patient profile + this doctor's own appointment history with them.
        Returns None if this patient has never had an appointment with this doctor —
        the caller (backend/main.py) turns that into a 404, which is what stops one
        doctor from browsing another doctor's patients by guessing an id.
        """
        if not self.doctor_has_patient(doctor_id, patient_id):
            return None

        profile = self.get_patient(patient_id) or {"id": patient_id}
        appts = self.get_appointments_by_doctor(doctor_id)
        history = sorted(
            (a for a in appts if a["patient_id"] == patient_id),
            key=lambda a: (a["appointment_date"], a["appointment_time"]),
            reverse=True,
        )
        return {"patient": profile, "appointments": history}

    # ============ Doctor Notes ============

    def create_doctor_note(self, doctor_id: str, patient_id: str, note: str, appointment_id: Optional[str] = None) -> Dict[str, Any]:
        response = self.client.table("doctor_notes").insert({
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "appointment_id": appointment_id,
            "note": note,
        }).execute()
        return response.data[0] if response.data else {}

    def get_doctor_notes(self, doctor_id: str, patient_id: str) -> List[Dict[str, Any]]:
        """Notes this doctor wrote about this patient — never another doctor's notes."""
        response = self.client.table("doctor_notes") \
            .select("*") \
            .eq("doctor_id", doctor_id) \
            .eq("patient_id", patient_id) \
            .order("created_at", desc=True) \
            .execute()
        return response.data if response.data else []

    # ============ Availability (weekly schedule editor) ============

    def upsert_doctor_schedules(self, doctor_id: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace a doctor's weekly availability for the given days (upsert on the
        (doctor_id, day_of_week) unique constraint already in the schema)."""
        payload = [{"doctor_id": doctor_id, **row} for row in rows]
        response = self.client.table("doctor_schedules").upsert(payload, on_conflict="doctor_id,day_of_week").execute()
        return response.data if response.data else []

    # ============ Notifications ============

    def create_notification(
        self, doctor_id: str, type: str, title: str, message: str, appointment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        response = self.client.table("doctor_notifications").insert({
            "doctor_id": doctor_id,
            "appointment_id": appointment_id,
            "type": type,
            "title": title,
            "message": message,
        }).execute()
        return response.data[0] if response.data else {}

    def get_notifications(self, doctor_id: str, unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List notifications, each enriched with a summary of the appointment it's
        about (confirmation number, patient, date/time) when it has one — this is
        what lets the dashboard bell be click-through-to-appointment/patient
        instead of just a text alert.
        """
        query = self.client.table("doctor_notifications").select("*").eq("doctor_id", doctor_id)
        if unread_only:
            query = query.eq("is_read", False)
        response = query.order("created_at", desc=True).limit(limit).execute()
        notifications = response.data if response.data else []

        appt_ids = list({n["appointment_id"] for n in notifications if n.get("appointment_id")})
        if not appt_ids:
            return notifications

        appts_resp = self.client.table("appointments") \
            .select("id, confirmation_number, patient_id, appointment_date, appointment_time, status") \
            .in_("id", appt_ids) \
            .execute()
        appts_by_id = {a["id"]: a for a in (appts_resp.data or [])}
        patients = self.get_patients_by_ids([a["patient_id"] for a in appts_by_id.values()])

        for n in notifications:
            appt = appts_by_id.get(n.get("appointment_id"))
            if not appt:
                continue
            patient = patients.get(appt["patient_id"], {})
            n["appointment"] = {
                "confirmation_number": appt["confirmation_number"],
                "patient_id": appt["patient_id"],
                "patient_name": patient.get("full_name") or patient.get("email") or "Unknown patient",
                "date": appt["appointment_date"],
                "time": appt["appointment_time"],
                "status": appt["status"],
            }
        return notifications

    def count_unread_notifications(self, doctor_id: str) -> int:
        response = self.client.table("doctor_notifications") \
            .select("id", count="exact") \
            .eq("doctor_id", doctor_id) \
            .eq("is_read", False) \
            .execute()
        return response.count or 0

    def mark_notification_read(self, notification_id: str, doctor_id: str) -> Optional[Dict[str, Any]]:
        """Scoped to doctor_id so a doctor can't mark (or even probe the existence
        of) another doctor's notification by guessing an id."""
        response = self.client.table("doctor_notifications") \
            .update({"is_read": True}) \
            .eq("id", notification_id) \
            .eq("doctor_id", doctor_id) \
            .execute()
        return response.data[0] if response.data else None

    def mark_all_notifications_read(self, doctor_id: str) -> int:
        response = self.client.table("doctor_notifications") \
            .update({"is_read": True}) \
            .eq("doctor_id", doctor_id) \
            .eq("is_read", False) \
            .execute()
        return len(response.data) if response.data else 0

    def generate_due_reminders(self, doctor_id: str) -> int:
        """
        Create 'appointment_reminder' notifications for this doctor's confirmed
        appointments happening today or tomorrow, if one hasn't already been sent
        for that appointment. Runs lazily whenever the doctor opens their
        notifications (no background scheduler in this project) — cheap since it's
        scoped to one doctor's next ~48h of appointments.
        """
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        upcoming = self.get_appointments_by_doctor(
            doctor_id, date_from=today.isoformat(), date_to=tomorrow.isoformat(), status="confirmed"
        )
        if not upcoming:
            return 0

        appt_ids = [a["id"] for a in upcoming]
        existing = self.client.table("doctor_notifications") \
            .select("appointment_id") \
            .eq("doctor_id", doctor_id) \
            .eq("type", "appointment_reminder") \
            .in_("appointment_id", appt_ids) \
            .execute()
        already_reminded = {row["appointment_id"] for row in (existing.data or [])}

        patients = self.get_patients_by_ids([a["patient_id"] for a in upcoming])
        created = 0
        for a in upcoming:
            if a["id"] in already_reminded:
                continue
            patient = patients.get(a["patient_id"], {})
            patient_name = patient.get("full_name") or patient.get("email") or "A patient"
            self.create_notification(
                doctor_id=doctor_id,
                type="appointment_reminder",
                title="Upcoming appointment",
                message=f"Reminder: appointment with {patient_name} on {a['appointment_date']} at {a['appointment_time'][:5]}.",
                appointment_id=a["id"],
            )
            created += 1
        return created

    # ============ Diet Plans (AI Diet Generator history) ============

    def create_diet_plan(self, patient_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        response = self.client.table("diet_plans").insert({"patient_id": patient_id, **data}).execute()
        return response.data[0] if response.data else {}

    def get_diet_plans_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        response = self.client.table("diet_plans") \
            .select("*") \
            .eq("patient_id", patient_id) \
            .order("created_at", desc=True) \
            .execute()
        return response.data if response.data else []

    def get_diet_plans_for_doctor(self, doctor_id: str) -> List[Dict[str, Any]]:
        """All diet plans belonging to any patient of this doctor — powers the
        dashboard's top-level 'Diet Plans' section (see also get_diet_plans_by_patient
        for the per-patient view on the patient detail page)."""
        patient_ids = list({a["patient_id"] for a in self.get_appointments_by_doctor(doctor_id)})
        if not patient_ids:
            return []
        response = self.client.table("diet_plans") \
            .select("*") \
            .in_("patient_id", patient_ids) \
            .order("created_at", desc=True) \
            .execute()
        plans = response.data if response.data else []
        patients = self.get_patients_by_ids(patient_ids)
        for plan in plans:
            profile = patients.get(plan["patient_id"], {})
            plan["patient_name"] = profile.get("full_name") or profile.get("email") or "Unknown patient"
        return plans

    # ============ Health Queries (AI assistant history) ============

    def create_health_query(self, patient_id: str, question: str, answer: Optional[str], source: Optional[str]) -> Dict[str, Any]:
        response = self.client.table("health_queries").insert({
            "patient_id": patient_id, "question": question, "answer": answer, "source": source,
        }).execute()
        return response.data[0] if response.data else {}

    def get_health_queries_by_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        response = self.client.table("health_queries") \
            .select("*") \
            .eq("patient_id", patient_id) \
            .order("created_at", desc=True) \
            .execute()
        return response.data if response.data else []

    def get_health_queries_for_doctor(self, doctor_id: str) -> List[Dict[str, Any]]:
        """All health-assistant query history belonging to any patient of this
        doctor — powers the dashboard's top-level 'Health Queries' section."""
        patient_ids = list({a["patient_id"] for a in self.get_appointments_by_doctor(doctor_id)})
        if not patient_ids:
            return []
        response = self.client.table("health_queries") \
            .select("*") \
            .in_("patient_id", patient_ids) \
            .order("created_at", desc=True) \
            .execute()
        queries = response.data if response.data else []
        patients = self.get_patients_by_ids(patient_ids)
        for q in queries:
            profile = patients.get(q["patient_id"], {})
            q["patient_name"] = profile.get("full_name") or profile.get("email") or "Unknown patient"
        return queries

    def reschedule_appointment(self, confirmation_number: str, date: str, time: str) -> Optional[Dict[str, Any]]:
        response = self.client.table("appointments") \
            .update({"appointment_date": date, "appointment_time": time}) \
            .eq("confirmation_number", confirmation_number) \
            .execute()
        return response.data[0] if response.data else None

    def get_patients_by_ids(self, patient_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Batch-fetch patient profiles keyed by id. appointments.patient_id has no FK
        to patients.id in the schema, so PostgREST can't auto-embed it the way it
        does for doctors — this two-step fetch-and-merge is the reliable approach.
        """
        if not patient_ids:
            return {}
        response = self.client.table("patients").select("id, full_name, phone, email, date_of_birth, allergies").in_("id", list(set(patient_ids))).execute()
        return {p["id"]: p for p in (response.data or [])}

    def update_appointment_status(self, confirmation_number: str, status: str, notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Update an appointment's status (e.g. 'completed', 'no_show', 'cancelled') — used by the doctor dashboard."""
        update_data = {"status": status}
        if notes is not None:
            update_data["notes"] = notes
        response = self.client.table("appointments").update(update_data).eq("confirmation_number", confirmation_number).execute()
        return response.data[0] if response.data else None

    def get_available_doctors(self, specialty: str, date: str, time: str) -> List[Dict[str, Any]]:
        """Get available doctors for a specific date/time who don't have conflicts"""
        # Get all doctors of this specialty
        doctors = self.get_doctors(specialty)
        
        if not doctors:
            return []
        
        available_doctors = []
        
        for doctor in doctors:
            # Check if doctor already has appointment at this time
            conflict = self.check_doctor_conflict(doctor['id'], date, time)
            
            # Check if it's during their working hours
            weekday = datetime.strptime(date, "%Y-%m-%d").weekday()  # 0=Monday
            
            schedules = self.client.table("doctor_schedules") \
                .select("*") \
                .eq("doctor_id", doctor['id']) \
                .eq("day_of_week", weekday) \
                .eq("is_available", True) \
                .execute()
            
            if not conflict and schedules.data:
                # Check time is within working hours
                for schedule in schedules.data:
                    start = schedule['start_time']
                    end = schedule['end_time']
                    
                    if start <= time <= end:
                        available_doctors.append(doctor)
                        break
        
        return available_doctors


# Global database instance
db = Database()


def get_db() -> Database:
    """Get database instance"""
    return db