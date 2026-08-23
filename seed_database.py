#!/usr/bin/env python3
"""
Database Seeding Script for Healthcare MCP Server
Run this after setting up Supabase tables to populate initial data
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Windows consoles default to a legacy codepage (e.g. cp1252) that can't
# encode the emoji used in print statements throughout this script — same fix
# as backend/main.py.
if sys.stdout.encoding is not None and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database import get_db, DEMO_DOCTORS
from backend.auth import new_admin_client

load_dotenv()

DOCTOR_DEFAULT_PASSWORD = "Doctor@123"
PATIENT_DEMO_PASSWORD = "Patient@123"

# Demo patients used to showcase the full patient -> appointment -> doctor
# notification -> doctor confirmation flow described in the task spec.
DEMO_PATIENTS = [
    {
        "email": "harshini.demo@healthcare-demo.com",
        "full_name": "Harshini Reddy",
        "phone": "+91 98765 43210",
        "date_of_birth": "1996-04-12",
        "allergies": ["Dust", "Pollen"],
    },
    {
        "email": "rohan.demo@healthcare-demo.com",
        "full_name": "Rohan Mehta",
        "phone": "+91 98765 12345",
        "date_of_birth": "1988-11-02",
        "allergies": ["Peanuts"],
    },
]


def seed_doctor_logins():
    """
    Provision a Supabase Auth login for each doctor (they're pre-seeded staff,
    not self-signup) and link it via doctors.auth_user_id. Requires the
    'auth_user_id' column from supabase_schema.sql's DOCTOR LOGIN section —
    run that in the Supabase SQL Editor first if this fails with a missing
    column error.
    """
    db = get_db()
    admin = new_admin_client()
    doctors = db.get_doctors()

    provisioned = []
    for doctor in doctors:
        if doctor.get("auth_user_id"):
            provisioned.append(doctor)
            continue

        email = doctor.get("email")
        if not email:
            print(f"   ⚠️  Skipping {doctor['name']} — no email on file")
            continue

        try:
            created = admin.auth.admin.create_user({
                "email": email,
                "password": DOCTOR_DEFAULT_PASSWORD,
                "email_confirm": True,
                "user_metadata": {"full_name": doctor["name"], "role": "doctor"},
            })
            auth_user_id = created.user.id
        except Exception as e:
            # Already registered (e.g. re-running this script) — look it up instead.
            if "already" in str(e).lower() and "registered" in str(e).lower():
                existing = None
                page = 1
                while True:
                    resp = admin.auth.admin.list_users(page=page, per_page=200)
                    users = resp if isinstance(resp, list) else getattr(resp, "users", resp)
                    if not users:
                        break
                    existing = next((u for u in users if u.email and u.email.lower() == email.lower()), None)
                    if existing or len(users) < 200:
                        break
                    page += 1
                if not existing:
                    print(f"   ⚠️  {doctor['name']}: couldn't find or create auth account for {email}: {e}")
                    continue
                auth_user_id = existing.id
            else:
                print(f"   ⚠️  {doctor['name']}: {str(e)[:80]}")
                continue

        db.set_doctor_auth_user(doctor["id"], auth_user_id)
        provisioned.append({**doctor, "auth_user_id": auth_user_id})

    return provisioned


def seed_demo_patients():
    """
    Provision a Supabase Auth login + patients profile for each demo patient
    (mirrors seed_doctor_logins, but for patients so they can be signed in to
    demonstrate the dashboard). Safe to re-run — looks up existing accounts by
    email instead of erroring.
    """
    db = get_db()
    admin = new_admin_client()

    provisioned = []
    for demo in DEMO_PATIENTS:
        email = demo["email"]
        try:
            created = admin.auth.admin.create_user({
                "email": email,
                "password": PATIENT_DEMO_PASSWORD,
                "email_confirm": True,
                "user_metadata": {"full_name": demo["full_name"]},
            })
            user_id = created.user.id
        except Exception as e:
            if "already" in str(e).lower() and "registered" in str(e).lower():
                existing = None
                page = 1
                while True:
                    resp = admin.auth.admin.list_users(page=page, per_page=200)
                    users = resp if isinstance(resp, list) else getattr(resp, "users", resp)
                    if not users:
                        break
                    existing = next((u for u in users if u.email and u.email.lower() == email.lower()), None)
                    if existing or len(users) < 200:
                        break
                    page += 1
                if not existing:
                    print(f"   ⚠️  {demo['full_name']}: couldn't find or create account for {email}: {e}")
                    continue
                user_id = existing.id
            else:
                print(f"   ⚠️  {demo['full_name']}: {str(e)[:80]}")
                continue

        patient = db.upsert_patient({
            "id": user_id,
            "email": email,
            "full_name": demo["full_name"],
            "phone": demo["phone"],
            "date_of_birth": demo["date_of_birth"],
            "allergies": demo["allergies"],
        })
        provisioned.append(patient)

    return provisioned


def seed_demo_appointments_and_history(demo_patients):
    """
    Create sample appointments/notes/diet plans/health queries across the 3
    named demo doctors, so the full patient -> appointment (auto-confirmed) ->
    doctor notification flow can be demonstrated immediately after seeding,
    without needing to book anything by hand first.

    Uses the real booking.book() tool (not a raw insert) for two of the
    appointments so the exact same code path patients use also creates the
    doctor notifications — this doubles as an end-to-end smoke test of that flow.
    """
    from backend.tools import booking as booking_tool

    db = get_db()
    by_email = {p["email"]: p for p in demo_patients}
    harshini = by_email.get("harshini.demo@healthcare-demo.com")
    rohan = by_email.get("rohan.demo@healthcare-demo.com")

    if not harshini or not rohan:
        print("   ⚠️  Demo patients missing — skipping demo appointments/history")
        return []

    created_confirmations = []

    # Skip entirely on a re-run — this patient already has appointment history.
    if db.get_appointments_by_patient(harshini["id"]):
        print("   ↩️  Demo appointments already exist — skipping (re-run seed_all to add more manually if needed)")
        return created_confirmations

    today = datetime.now().date()

    # 1) Harshini -> Dr. Priya (Dermatology): the flagship booking used
    #    throughout the task spec's example flow. Auto-confirmed (no doctor
    #    approval step) — this call is what creates Dr. Priya's notification.
    # NOTE: 10:30 (as in the original task example) isn't bookable — clinic
    # slots are in SLOT_INTERVAL_MINUTES (20-minute) increments, so 10:20 is
    # the nearest valid slot. book() would otherwise silently fail validation
    # and this appointment just wouldn't exist.
    result = booking_tool.book(
        user_id=harshini["id"],
        date="2026-08-25",
        time="10:20",
        specialty="dermatology",
        reason="Skin consultation",
        doctor_id="doc_101",
        patient_display=harshini["full_name"],
    )
    if result.get("confirmation_number"):
        created_confirmations.append(result["confirmation_number"])
        print(f"   ✅ Harshini -> Dr. Priya, 2026-08-25 10:20 (confirmed) — {result['confirmation_number']}")
    else:
        print(f"   ⚠️  Flagship demo booking failed: {result.get('message')}")

    # 2) A completed appointment in the recent past between the same pair, so
    #    the patient-detail "Appointment History" table isn't empty on day one.
    past_appt = db.create_appointment({
        "confirmation_number": f"APT-{90000 + hash('harshini-past') % 9999}",
        "patient_id": harshini["id"],
        "doctor_id": "doc_101",
        "appointment_date": (today - timedelta(days=4)).isoformat(),
        "appointment_time": "10:30",
        "specialty": "dermatology",
        "reason": "Skin consultation",
        "status": "completed",
    })
    db.create_doctor_note(
        doctor_id="doc_101",
        patient_id=harshini["id"],
        note="Patient reported improvement after previous treatment. Follow-up recommended after 2 weeks.",
        appointment_id=past_appt.get("id"),
    )
    print(f"   ✅ Harshini -> Dr. Priya, {(today - timedelta(days=4)).isoformat()} (completed, with doctor note)")

    # 3) Harshini's diet plan + health query history (from the existing AI
    #    Diet Generator / health-query assistant), so the doctor has something
    #    to review under Diet Plans / Health Queries.
    db.create_diet_plan(harshini["id"], {
        "preferences": "vegetarian",
        "daily_calories": 1800,
        "allergies": ["Dust", "Pollen"],
        "plan_text": None,
        "meals": {
            "Breakfast": "Vegetable oatmeal with berries (400 cal)",
            "Morning Snack": "Greek yogurt with honey (150 cal)",
            "Lunch": "Quinoa bowl with roasted vegetables and paneer (500 cal)",
            "Afternoon Snack": "Fresh fruit and almonds (200 cal)",
            "Dinner": "Grilled tofu with steamed greens (550 cal)",
        },
        "source": "template",
    })
    db.create_health_query(
        harshini["id"],
        question="I'm experiencing dry and itchy skin. What could be causing it?",
        answer=(
            "Dry, itchy skin is commonly caused by low humidity, hot showers, harsh soaps, "
            "eczema, or seasonal allergies. Using a fragrance-free moisturizer and lukewarm "
            "water often helps. ⚕️ Consult a healthcare professional before making medical decisions."
        ),
        source="template",
    )
    print("   ✅ Harshini's diet plan + health-query history seeded")

    # 4) Rohan -> Dr. Rahul (Cardiology): two confirmed appointments, so Dr.
    #    Rahul's dashboard has its own, completely separate data to
    #    demonstrate doctor-to-doctor isolation.
    confirmed_appt = db.create_appointment({
        "confirmation_number": f"APT-{90000 + hash('rohan-confirmed') % 9999}",
        "patient_id": rohan["id"],
        "doctor_id": "doc_102",
        "appointment_date": (today + timedelta(days=2)).isoformat(),
        "appointment_time": "09:00",
        "specialty": "cardiology",
        "reason": "Routine blood pressure check",
        "status": "confirmed",
    })
    created_confirmations.append(confirmed_appt.get("confirmation_number"))
    print(f"   ✅ Rohan -> Dr. Rahul, {(today + timedelta(days=2)).isoformat()} 09:00 (confirmed)")

    result2 = booking_tool.book(
        user_id=rohan["id"],
        date="2026-08-27",
        time="09:20",
        specialty="cardiology",
        reason="Occasional chest tightness after exercise",
        doctor_id="doc_102",
        patient_display=rohan["full_name"],
    )
    if result2.get("confirmation_number"):
        created_confirmations.append(result2["confirmation_number"])
        print(f"   ✅ Rohan -> Dr. Rahul, 2026-08-27 09:20 (confirmed) — {result2['confirmation_number']}")

    db.create_health_query(
        rohan["id"],
        question="Is occasional chest tightness after exercise something to worry about?",
        answer=(
            "Chest tightness during or after exercise can have many causes, from muscle strain "
            "to cardiovascular causes that need evaluation. ⚕️ Consult a healthcare professional "
            "before making medical decisions, especially given your upcoming cardiology visit."
        ),
        source="template",
    )

    return created_confirmations


def seed_demo_nutrition_appointment(demo_patients):
    """
    Give Dr. Ananya (nutrition, doc_103) a demo appointment too, so all three
    Doctor Dashboard demo doctors (see DEMO_DOCTORS in backend/database.py)
    have something to show — not just Dr. Priya and Dr. Rahul.

    Kept as its own step (rather than folded into
    seed_demo_appointments_and_history) so it checks its own idempotency and
    still runs even after that function's own history already exists and it
    skips itself on a re-run.
    """
    from backend.tools import booking as booking_tool

    db = get_db()
    by_email = {p["email"]: p for p in demo_patients}
    harshini = by_email.get("harshini.demo@healthcare-demo.com")
    if not harshini:
        print("   ⚠️  Demo patient missing — skipping Dr. Ananya demo appointment")
        return None

    existing = db.get_appointments_by_patient(harshini["id"])
    if any(a.get("doctor_id") == "doc_103" for a in existing):
        print("   ↩️  Harshini already has an appointment with Dr. Ananya — skipping")
        return None

    result = booking_tool.book(
        user_id=harshini["id"],
        date="2026-08-26",
        time="11:00",
        specialty="nutrition",
        reason="Diet consultation - follow-up on vegetarian meal plan",
        doctor_id="doc_103",
        patient_display=harshini["full_name"],
    )
    if result.get("confirmation_number"):
        print(f"   ✅ Harshini -> Dr. Ananya, 2026-08-26 11:00 (confirmed) — {result['confirmation_number']}")
        return result["confirmation_number"]

    print(f"   ⚠️  Dr. Ananya demo booking failed: {result.get('message')}")
    return None


def seed_all():
    """Seed all database tables with initial data"""
    print("=" * 60)
    print("🏥 Healthcare MCP Server - Database Seeder")
    print("=" * 60)

    db = get_db()

    try:
        # Seed doctors
        print("\n📋 Step 1: Seeding doctors...")
        doctor_count = db.seed_doctors()
        print(f"   ✅ Seeded {doctor_count} doctors")

        # Seed schedules
        print("\n📅 Step 2: Seeding doctor schedules...")
        schedule_count = db.seed_schedules()
        print(f"   ✅ Seeded {schedule_count} schedules")

        # Seed doctor login accounts
        print("\n🔐 Step 3: Seeding doctor login accounts...")
        try:
            doctors = seed_doctor_logins()
            print(f"   ✅ {len(doctors)} doctor accounts ready")
            print(f"\n   Doctor login credentials (shared password for this demo):")
            print(f"   Password: {DOCTOR_DEFAULT_PASSWORD}")
            for doc in doctors:
                print(f"     • {doc['email']}  ({doc['name']} — {doc['specialty']})")
        except Exception as e:
            print(f"   ⚠️  Doctor login seeding failed: {e}")
            print("   Make sure you've run the 'DOCTOR LOGIN' section of supabase_schema.sql in the Supabase SQL Editor.")

        # Seed demo patients
        print("\n🧑‍🤝‍🧑 Step 4: Seeding demo patient accounts...")
        demo_patients = []
        try:
            demo_patients = seed_demo_patients()
            print(f"   ✅ {len(demo_patients)} demo patient account(s) ready")
            print(f"\n   Patient login credentials (shared password for this demo):")
            print(f"   Password: {PATIENT_DEMO_PASSWORD}")
            for p in demo_patients:
                print(f"     • {p['email']}  ({p.get('full_name')})")
        except Exception as e:
            print(f"   ⚠️  Demo patient seeding failed: {e}")

        # Seed demo appointments / notifications / notes / diet plans / health queries
        print("\n📆 Step 5: Seeding demo appointments & history...")
        try:
            if demo_patients:
                confirmations = seed_demo_appointments_and_history(demo_patients)
                print(f"   ✅ Demo appointments ready ({len(confirmations)} confirmation number(s))")
            else:
                print("   ↩️  Skipped — no demo patients available")
        except Exception as e:
            print(f"   ⚠️  Demo appointment seeding failed: {e}")

        # Give Dr. Ananya (the 3rd DEMO_DOCTORS entry) a demo appointment too
        print("\n🥗 Step 6: Seeding Dr. Ananya's demo appointment...")
        try:
            if demo_patients:
                seed_demo_nutrition_appointment(demo_patients)
            else:
                print("   ↩️  Skipped — no demo patients available")
        except Exception as e:
            print(f"   ⚠️  Dr. Ananya demo appointment seeding failed: {e}")

        print("\n" + "=" * 60)
        print("✨ Database seeding complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Start the server: ./start.sh")
        print(f"2. Sign in as a doctor at /doctor-dashboard (e.g. {DEMO_DOCTORS[0]['email']})")
        print("3. Sign in as a patient at / (e.g. harshini.demo@healthcare-demo.com) to see the booking flow")

    except Exception as e:
        print(f"\n❌ Seeding failed: {e}")
        print("\nTroubleshooting:")
        print("- Verify SUPABASE_URL and SUPABASE_KEY in .env")
        print("- Ensure you've run supabase_schema.sql in Supabase SQL Editor")
        sys.exit(1)


def verify_connection():
    """Verify database connection works"""
    print("\n🔌 Testing database connection...")
    try:
        db = get_db()
        # Try a simple query
        response = db.client.table("doctors").select("count", count="exact").execute()
        print("   ✅ Connection successful!")
        return True
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return False


if __name__ == "__main__":
    print("\nChecking environment...")
    
    # Check env vars
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("\n❌ Missing environment variables!")
        print("Add to your .env file:")
        print("  SUPABASE_URL=https://your-project.supabase.co")
        print("  SUPABASE_KEY=your-anon-key")
        print("\nGet these from: https://supabase.com/dashboard/project/_/settings/api")
        sys.exit(1)
    
    if verify_connection():
        seed_all()
    else:
        print("\nPlease check your Supabase credentials and try again.")
        sys.exit(1)