
from fastapi import FastAPI, Body, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from pydantic import BaseModel
from backend.mcp import tools, call_tool, get_available_tools
from backend.agent import run_agent_turn
from backend.database import get_db
from backend.auth import (
    get_current_patient,
    get_current_patient_optional,
    get_current_doctor,
    new_auth_client,
    new_admin_client,
    CurrentPatient,
    CurrentDoctor,
)
from backend.tools import booking as booking_tool
from typing import Dict, Any, List, Optional
import logging
import json
import os
import re
import sys
from datetime import datetime

# Windows consoles default to a legacy codepage (e.g. cp1252) that can't
# encode the emoji used in log messages throughout this codebase. Force
# UTF-8 on stdio so logging doesn't crash mid-request.
if sys.stdout.encoding is not None and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# ENVIRONMENT switches a few things below: log verbosity and, in main.py (the
# launcher), whether uvicorn runs with --reload. Defaults to "development" so
# nothing changes for existing local setups unless ENVIRONMENT is set.
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_default_log_level = "DEBUG" if ENVIRONMENT != "production" else "INFO"
LOG_LEVEL = os.getenv("LOG_LEVEL", _default_log_level).upper()

# Root logger stays at INFO regardless — this also governs third-party
# libraries (httpx, mistralai, etc.), and their DEBUG output is internal
# connection-level tracing, not something worth showing here. Only this
# app's own loggers (backend.*, i.e. every logging.getLogger(__name__) in
# this package) go to LOG_LEVEL, which is what actually gates the per-field
# tool-call tracing added throughout backend/tools/*.py.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger("backend").setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Healthcare MCP API",
    description="Model Context Protocol API for Healthcare Management",
    version="1.0.0"
)

# CORS: restrict to explicit origins instead of "*". The frontend is served
# by this same FastAPI app, so real usage doesn't need cross-origin calls at
# all — "*" only ever mattered for letting arbitrary other sites call this
# API with credentials, which is what made it a real hardening gap, not just
# a formality (Starlette's CORSMiddleware, when allow_credentials=True and
# allow_origins=["*"], echoes back the caller's actual Origin header instead
# of a literal "*", so it behaved as "any origin, with credentials").
# Override via ALLOWED_ORIGINS (comma-separated) for other deployments.
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api")
def api_info():
    return {
        "message": "Healthcare MCP API",
        "endpoints": {
            "tools": "/mcp/tools",
            "call": "/mcp/call",
            "docs": "/docs"
        }
    }


# ── Request models ──────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    allergies: Optional[List[str]] = None


DOCTOR_SETTABLE_STATUSES = ("pending", "confirmed", "completed", "cancelled", "rejected", "no_show")


class DoctorStatusUpdateRequest(BaseModel):
    status: str  # one of DOCTOR_SETTABLE_STATUSES
    notes: Optional[str] = None


class RescheduleRequest(BaseModel):
    date: str
    time: str


class DoctorProfileUpdateRequest(BaseModel):
    phone: Optional[str] = None
    bio: Optional[str] = None
    qualifications: Optional[List[str]] = None
    years_experience: Optional[int] = None
    image_url: Optional[str] = None
    hospital: Optional[str] = None
    consultation_fee: Optional[float] = None


class ChatRequest(BaseModel):
    message: str
    session_id: str


class AvailabilityRow(BaseModel):
    day_of_week: int  # 0=Monday .. 6=Sunday
    start_time: str
    end_time: str
    is_available: bool = True


class AvailabilityUpdateRequest(BaseModel):
    schedules: List[AvailabilityRow]


class DoctorNoteRequest(BaseModel):
    note: str
    appointment_id: Optional[str] = None


# ── Auth endpoints ───────────────────────────────────────────────────────
@app.post("/api/auth/signup")
def signup(payload: SignupRequest):
    """
    Create a Supabase Auth account and a matching patient profile.

    This project has no outbound email configured (no SMTP provider set up in
    Supabase), so the normal sign_up() flow — which requires the patient to
    click a confirmation link that never actually gets emailed — would leave
    every new signup permanently stuck. Instead, the account is created
    already confirmed via the Auth Admin API (service_role key required),
    then immediately signed in so the caller gets a real session right away.
    """
    if "@" not in payload.email:
        raise HTTPException(status_code=400, detail="Please provide a valid email address")

    admin_client = new_admin_client()
    try:
        created = admin_client.auth.admin.create_user({
            "email": payload.email,
            "password": payload.password,
            "email_confirm": True,
            "user_metadata": {"full_name": payload.full_name} if payload.full_name else {},
        })
    except Exception as e:
        message = str(e)
        if "already" in message.lower() and "registered" in message.lower():
            raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in instead.")
        raise HTTPException(status_code=400, detail=f"Signup failed: {message}")

    if not created.user:
        raise HTTPException(status_code=400, detail="Signup failed")

    db = get_db()
    try:
        patient = db.upsert_patient({
            "id": created.user.id,
            "email": payload.email,
            "full_name": payload.full_name,
        })
    except Exception as e:
        logger.warning(f"⚠️  Failed to create patient profile for {payload.email}: {e}")
        patient = {"id": created.user.id, "email": payload.email, "full_name": payload.full_name}

    # Account is already confirmed - sign in immediately so the caller gets a
    # usable session without any email step.
    client = new_auth_client()
    access_token = None
    try:
        result = client.auth.sign_in_with_password({"email": payload.email, "password": payload.password})
        if result.session:
            access_token = result.session.access_token
    except Exception as e:
        logger.warning(f"⚠️  Auto sign-in after signup failed for {payload.email}: {e}")

    if access_token:
        return {
            "message": "Account created successfully",
            "access_token": access_token,
            "patient": patient,
        }

    return {
        "message": "Account created. Please sign in.",
        "access_token": None,
        "patient": patient,
    }


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    """Sign in with email/password and return a bearer token."""
    client = new_auth_client()
    try:
        result = client.auth.sign_in_with_password({"email": payload.email, "password": payload.password})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not result.session or not result.user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    db = get_db()
    patient = db.get_patient(result.user.id)
    if not patient:
        # Profile row missing (e.g. account created before this table existed) - backfill it
        patient = db.upsert_patient({"id": result.user.id, "email": result.user.email})

    return {
        "message": "Signed in successfully",
        "access_token": result.session.access_token,
        "patient": patient,
    }


@app.get("/api/auth/me")
def whoami(current: CurrentPatient = Depends(get_current_patient)):
    """Return the current patient's profile (validates the bearer token)."""
    db = get_db()
    patient = db.get_patient(current.id) or db.upsert_patient({"id": current.id, "email": current.email})
    return {"patient": patient}


# ── Doctor dashboard endpoints ──────────────────────────────────────────
# Doctors are provisioned, not self-signup (see seed_database.py) — a doctors
# row is linked to a Supabase Auth user via `auth_user_id`. get_current_doctor
# enforces that only such a linked account can reach these endpoints.

@app.post("/api/doctor/login")
def doctor_login(payload: LoginRequest):
    """Sign in as a doctor with email/password and return a bearer token."""
    client = new_auth_client()
    try:
        result = client.auth.sign_in_with_password({"email": payload.email, "password": payload.password})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not result.session or not result.user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    db = get_db()
    doctor = db.get_doctor_by_auth_user_id(result.user.id)
    if not doctor:
        raise HTTPException(status_code=403, detail="This account is not registered as a doctor.")

    return {
        "message": "Signed in successfully",
        "access_token": result.session.access_token,
        "doctor": {"id": doctor["id"], "name": doctor["name"], "specialty": doctor["specialty"]},
    }


@app.get("/api/doctor/me")
def doctor_whoami(current: CurrentDoctor = Depends(get_current_doctor)):
    """Return the current doctor's profile (validates the bearer token)."""
    return {"doctor": {"id": current.doctor_id, "name": current.name, "specialty": current.specialty}}


@app.get("/api/doctor/appointments")
def doctor_appointments(
    date: Optional[str] = None,
    status: Optional[str] = None,
    range: Optional[str] = None,  # 'today' | 'upcoming' | 'all'
    current: CurrentDoctor = Depends(get_current_doctor),
):
    """
    List the current doctor's appointments. Defaults to today's date (unchanged
    behavior for existing callers); pass range='upcoming' or range='all' to widen
    the window, and/or status=... to filter by appointment status.
    """
    db = get_db()
    today = datetime.now().date().isoformat()

    date_from = date_to = target_date = None
    if range == "upcoming":
        date_from = today
    elif range == "all":
        pass
    else:
        target_date = date or today

    appointments = db.get_appointments_by_doctor(
        current.doctor_id, date=target_date, status=status, date_from=date_from, date_to=date_to
    )
    patients = db.get_patients_by_ids([a["patient_id"] for a in appointments])

    formatted = []
    for appt in appointments:
        patient = patients.get(appt["patient_id"], {})
        formatted.append({
            "confirmation_number": appt["confirmation_number"],
            "patient_id": appt["patient_id"],
            "date": appt["appointment_date"],
            "time": appt["appointment_time"],
            "specialty": appt["specialty"],
            "reason": appt.get("reason"),
            "status": appt["status"],
            "booked_at": appt.get("booked_at"),
            "patient_name": patient.get("full_name") or patient.get("email") or "Unknown patient",
            "patient_phone": patient.get("phone"),
            "patient_email": patient.get("email"),
        })

    return {"date": target_date, "appointments": formatted}


@app.post("/api/doctor/appointments/{confirmation_number}/status")
def doctor_update_appointment_status(
    confirmation_number: str,
    payload: DoctorStatusUpdateRequest,
    current: CurrentDoctor = Depends(get_current_doctor),
):
    """
    Transition one of the doctor's own appointments: accept (-> confirmed),
    reject (-> rejected), mark completed, cancel, or mark no-show.
    """
    if payload.status not in DOCTOR_SETTABLE_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(DOCTOR_SETTABLE_STATUSES)}")

    db = get_db()
    appt = db.get_appointment_by_confirmation(confirmation_number)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["doctor_id"] != current.doctor_id:
        raise HTTPException(status_code=403, detail="This appointment doesn't belong to you")

    db.update_appointment_status(confirmation_number, payload.status, payload.notes)

    # Log the doctor's own accept action in their notification feed (pre-read —
    # it's their own action, not something they need alerting about).
    if payload.status == "confirmed":
        patient = db.get_patient(appt["patient_id"]) or {}
        patient_label = patient.get("full_name") or patient.get("email") or "the patient"
        db.create_notification(
            doctor_id=current.doctor_id,
            type="appointment_accepted",
            title="Appointment confirmed",
            message=f"You confirmed the appointment with {patient_label} on {appt['appointment_date']} at {appt['appointment_time'][:5]}.",
            appointment_id=appt.get("id"),
        )

    return {"message": f"Appointment marked as {payload.status}", "confirmation_number": confirmation_number, "status": payload.status}


@app.post("/api/doctor/appointments/{confirmation_number}/reschedule")
def doctor_reschedule_appointment(
    confirmation_number: str,
    payload: RescheduleRequest,
    current: CurrentDoctor = Depends(get_current_doctor),
):
    """Reschedule one of the doctor's own appointments to a new date/time."""
    db = get_db()
    appt = db.get_appointment_by_confirmation(confirmation_number)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["doctor_id"] != current.doctor_id:
        raise HTTPException(status_code=403, detail="This appointment doesn't belong to you")
    if appt["status"] in ("completed", "cancelled", "rejected"):
        raise HTTPException(status_code=400, detail=f"Cannot reschedule a {appt['status']} appointment")

    from backend.tools.booking import validate_date, validate_slot_interval, validate_business_hours
    for valid, error in (validate_date(payload.date), validate_slot_interval(payload.time), validate_business_hours(payload.time)):
        if not valid:
            raise HTTPException(status_code=400, detail=error)

    conflict = db.check_doctor_conflict(current.doctor_id, payload.date, payload.time)
    if conflict and conflict.get("confirmation_number") != confirmation_number:
        raise HTTPException(status_code=409, detail="You already have another appointment at that date/time")

    db.reschedule_appointment(confirmation_number, payload.date, payload.time)

    patient = db.get_patient(appt["patient_id"]) or {}
    patient_label = patient.get("full_name") or patient.get("email") or "the patient"
    db.create_notification(
        doctor_id=current.doctor_id,
        type="appointment_rescheduled",
        title="Appointment rescheduled",
        message=f"You rescheduled {patient_label}'s appointment to {payload.date} at {payload.time}.",
        appointment_id=appt.get("id"),
    )

    return {"message": "Appointment rescheduled", "confirmation_number": confirmation_number, "date": payload.date, "time": payload.time}


# ── Doctor profile & availability ────────────────────────────────────────
@app.get("/api/doctor/profile")
def doctor_get_profile(current: CurrentDoctor = Depends(get_current_doctor)):
    """Full profile for the current doctor, plus their weekly availability."""
    db = get_db()
    doctor = db.get_doctor_by_id(current.doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found")
    doctor = {k: v for k, v in doctor.items() if k != "auth_user_id"}
    schedule = db.get_doctor_schedule(current.doctor_id)
    return {"doctor": doctor, "availability": schedule}


@app.put("/api/doctor/profile")
def doctor_update_profile(payload: DoctorProfileUpdateRequest, current: CurrentDoctor = Depends(get_current_doctor)):
    """Update the current doctor's own editable profile fields."""
    db = get_db()
    fields: Dict[str, Any] = {}
    for field in ("phone", "bio", "qualifications", "years_experience", "image_url", "hospital", "consultation_fee"):
        value = getattr(payload, field)
        if value is not None:
            fields[field] = value
    doctor = db.update_doctor_profile(current.doctor_id, fields)
    return {"message": "Profile updated", "doctor": doctor}


@app.get("/api/doctor/availability")
def doctor_get_availability(current: CurrentDoctor = Depends(get_current_doctor)):
    """The current doctor's weekly recurring availability (used by patient booking too)."""
    db = get_db()
    return {"availability": db.get_doctor_schedule(current.doctor_id)}


@app.put("/api/doctor/availability")
def doctor_update_availability(payload: AvailabilityUpdateRequest, current: CurrentDoctor = Depends(get_current_doctor)):
    """
    Replace the current doctor's weekly availability. Once a slot is booked
    (an appointment exists for that date/time), it's still shown as occupied by
    get_available_slots regardless of these hours — this only controls which
    day/time windows are open for new bookings going forward.
    """
    time_re = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    for row in payload.schedules:
        if not (0 <= row.day_of_week <= 6):
            raise HTTPException(status_code=400, detail="day_of_week must be between 0 (Monday) and 6 (Sunday)")
        if not (time_re.match(row.start_time) and time_re.match(row.end_time)):
            raise HTTPException(status_code=400, detail="start_time/end_time must be in HH:MM 24-hour format")
        if row.start_time >= row.end_time:
            raise HTTPException(status_code=400, detail="start_time must be before end_time")

    db = get_db()
    rows = [r.model_dump() for r in payload.schedules]
    updated = db.upsert_doctor_schedules(current.doctor_id, rows)
    return {"message": "Availability updated", "availability": updated}


# ── Doctor dashboard summary ─────────────────────────────────────────────
@app.get("/api/doctor/dashboard/summary")
def doctor_dashboard_summary(current: CurrentDoctor = Depends(get_current_doctor)):
    """Everything the dashboard's top cards + overview sections need, in one call."""
    db = get_db()
    summary = db.get_dashboard_summary(current.doctor_id)
    notifications = db.get_notifications(current.doctor_id, limit=5)
    unread_count = db.count_unread_notifications(current.doctor_id)
    return {**summary, "recent_notifications": notifications, "unread_notifications": unread_count}


# ── My Patients ───────────────────────────────────────────────────────────
@app.get("/api/doctor/patients")
def doctor_list_patients(
    search: Optional[str] = None,
    filter: Optional[str] = None,  # 'new' | 'returning' | 'upcoming' | 'recent'
    current: CurrentDoctor = Depends(get_current_doctor),
):
    db = get_db()
    return {"patients": db.get_patients_for_doctor(current.doctor_id, search=search, filter=filter)}


@app.get("/api/doctor/patients/{patient_id}")
def doctor_get_patient(patient_id: str, current: CurrentDoctor = Depends(get_current_doctor)):
    """
    Full patient detail for the doctor: profile, appointment history with this
    doctor only, this doctor's own notes, and the patient's diet plans / health
    query history (if any) from the existing AI features. 404s if this patient
    has never had an appointment with the current doctor.
    """
    db = get_db()
    detail = db.get_patient_detail_for_doctor(current.doctor_id, patient_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Patient not found among your patients")

    return {
        "patient": detail["patient"],
        "appointments": detail["appointments"],
        "notes": db.get_doctor_notes(current.doctor_id, patient_id),
        "diet_plans": db.get_diet_plans_by_patient(patient_id),
        "health_queries": db.get_health_queries_by_patient(patient_id),
    }


@app.post("/api/doctor/patients/{patient_id}/notes")
def doctor_add_patient_note(
    patient_id: str, payload: DoctorNoteRequest, current: CurrentDoctor = Depends(get_current_doctor)
):
    """Add a private note (visible only to this doctor) for one of their patients."""
    db = get_db()
    if not db.doctor_has_patient(current.doctor_id, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found among your patients")
    note = db.create_doctor_note(current.doctor_id, patient_id, payload.note, payload.appointment_id)
    return {"message": "Note added", "note": note}


# ── Diet Plans / Health Queries (AI feature history, read-only for doctors) ─
@app.get("/api/doctor/diet-plans")
def doctor_list_diet_plans(current: CurrentDoctor = Depends(get_current_doctor)):
    db = get_db()
    return {"diet_plans": db.get_diet_plans_for_doctor(current.doctor_id)}


@app.get("/api/doctor/health-queries")
def doctor_list_health_queries(current: CurrentDoctor = Depends(get_current_doctor)):
    db = get_db()
    return {"health_queries": db.get_health_queries_for_doctor(current.doctor_id)}


# ── Notifications ─────────────────────────────────────────────────────────
@app.get("/api/doctor/notifications")
def doctor_list_notifications(unread_only: bool = False, current: CurrentDoctor = Depends(get_current_doctor)):
    db = get_db()
    db.generate_due_reminders(current.doctor_id)  # lazily materialize any due reminders first
    return {
        "notifications": db.get_notifications(current.doctor_id, unread_only=unread_only),
        "unread_count": db.count_unread_notifications(current.doctor_id),
    }


@app.get("/api/doctor/notifications/unread-count")
def doctor_unread_notification_count(current: CurrentDoctor = Depends(get_current_doctor)):
    db = get_db()
    return {"unread_count": db.count_unread_notifications(current.doctor_id)}


@app.post("/api/doctor/notifications/{notification_id}/read")
def doctor_mark_notification_read(notification_id: str, current: CurrentDoctor = Depends(get_current_doctor)):
    db = get_db()
    updated = db.mark_notification_read(notification_id, current.doctor_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Marked as read", "notification": updated}


@app.post("/api/doctor/notifications/read-all")
def doctor_mark_all_notifications_read(current: CurrentDoctor = Depends(get_current_doctor)):
    db = get_db()
    count = db.mark_all_notifications_read(current.doctor_id)
    return {"message": f"Marked {count} notification(s) as read"}


@app.put("/api/patients/me")
def update_profile(payload: ProfileUpdateRequest, current: CurrentPatient = Depends(get_current_patient)):
    """Update the current patient's profile."""
    db = get_db()
    data: Dict[str, Any] = {"id": current.id, "email": current.email}
    for field in ("full_name", "phone", "date_of_birth", "allergies"):
        value = getattr(payload, field)
        if value is not None:
            data[field] = value
    patient = db.upsert_patient(data)
    return {"message": "Profile updated", "patient": patient}


# ── Appointment endpoints (scoped to the authenticated patient) ─────────
@app.get("/api/appointments/me")
def my_appointments(current: CurrentPatient = Depends(get_current_patient)):
    """List the current patient's appointments, most recent first."""
    db = get_db()
    appointments = db.get_appointments_by_patient(current.id)

    formatted = []
    for appt in appointments:
        doc = appt.get("doctors") or {}
        formatted.append({
            "confirmation_number": appt["confirmation_number"],
            "date": appt["appointment_date"],
            "time": appt["appointment_time"],
            "specialty": appt["specialty"],
            "reason": appt.get("reason"),
            "status": appt["status"],
            "doctor_name": doc.get("name", "Unknown"),
        })

    return {"appointments": formatted}


@app.post("/api/appointments/{confirmation_number}/cancel")
def cancel_my_appointment(confirmation_number: str, current: CurrentPatient = Depends(get_current_patient)):
    """Cancel an appointment — only the patient who booked it may cancel it."""
    db = get_db()
    appt = db.get_appointment_by_confirmation(confirmation_number)

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.get("patient_id") != current.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own appointments")

    return booking_tool.cancel_appointment(confirmation_number=confirmation_number)

@app.post("/api/chat")
def chat(payload: ChatRequest = Body(...), authorization: Optional[str] = Header(None)):
    """
    Agentic chat endpoint: runs one patient message through the Mistral
    tool-calling loop (backend/agent.py) over the existing MCP tools.

    Auth is optional — anonymous patients can still ask health/diet
    questions and browse doctors; booking/cancelling requires a signed-in
    session, which the agent enforces itself (see agent.run_agent_turn).
    """
    message = (payload.message or "").strip()
    session_id = (payload.session_id or "").strip()

    if not message:
        return {"error": True, "message": "Message cannot be empty."}
    if not session_id:
        return {"error": True, "message": "Missing session_id."}

    current_patient = get_current_patient_optional(authorization)

    logger.info("=" * 80)
    logger.info(f"💬 CHAT [{session_id[:8]}] patient={current_patient.email if current_patient else 'anonymous'}")
    logger.info(f"   > {message}")

    result = run_agent_turn(session_id=session_id, user_message=message, current_patient=current_patient)

    logger.info(f"   < {result['reply']}")
    if result.get("executed_action"):
        logger.info(f"   ⚙️ executed: {result['executed_action']['tool']}")

    return result


@app.get("/mcp/tools")
def list_tools():
    """Get all available MCP tools with their schemas"""
    return {"tools": get_available_tools()}

@app.post("/mcp/call")
def mcp_call(payload: Dict[str, Any] = Body(...), authorization: Optional[str] = Header(None)):
    """
    Execute an MCP tool with provided arguments

    Request body:
    {
        "name": "tool_name",
        "args": { ... }
    }
    """
    name = payload.get("name")
    args = payload.get("args", {}) or {}

    if not name:
        logger.error("❌ Missing 'name' field in request")
        return {"error": "Missing 'name' field in request"}

    # Booking and cancellation are patient-owned actions: require a verified
    # session and ignore/ownership-check any patient identity the client sent,
    # rather than trusting a free-typed "Patient ID" string.
    if name == "book_appointment":
        current = get_current_patient(authorization)  # raises 401 if not signed in
        args["user_id"] = current.id
        args["patient_display"] = current.email

    elif name == "cancel_appointment":
        current = get_current_patient(authorization)
        confirmation_number = args.get("confirmation_number")
        db = get_db()
        appt = db.get_appointment_by_confirmation(confirmation_number) if confirmation_number else None
        if not appt or appt.get("patient_id") != current.id:
            return {"error": True, "message": "You can only cancel your own appointments."}

    # generate_diet / general_query work for anonymous chat too, but if the
    # caller happens to be a signed-in patient, quietly capture their identity
    # so the result can be persisted below for their doctor to review later.
    current_patient = get_current_patient_optional(authorization) if name in ("generate_diet", "general_query") else None

    # Log the incoming request
    logger.info("=" * 80)
    logger.info(f"🔧 TOOL CALL: {name}")
    logger.info(f"📥 INPUT ARGS:")
    for key, value in args.items():
        logger.info(f"   • {key}: {value}")
    logger.info("-" * 80)
    
    # Execute the tool
    result = call_tool(name, args)
    
    # Log the response
    if "error" in result:
        logger.error(f"❌ ERROR: {result.get('error')}")
        if "suggestion" in result:
            logger.info(f"💡 SUGGESTION: {result.get('suggestion')}")
    else:
        logger.info(f"✅ SUCCESS")
        logger.info(f"📤 OUTPUT:")
        
        # Pretty print the result
        if name == "book_appointment" and "confirmation_number" in result:
            logger.info(f"   🎫 Confirmation: {result['confirmation_number']}")
            logger.info(f"   👤 Patient: {result.get('details', {}).get('Patient', 'N/A')}")
            logger.info(f"   📅 Time: {result.get('details', {}).get('Appointment Time', 'N/A')}")
        elif name == "generate_diet" and "plan" in result:
            logger.info(f"   🥗 Diet: {result.get('preference', 'N/A')}")
            logger.info(f"   📊 Calories: {result.get('daily_calories', 'N/A')}")
            if result.get('plan'):
                logger.info(f"   📋 Meals: {len(result['plan']) if isinstance(result['plan'], dict) else 'Generated'}")
        elif name == "general_query" and "answer" in result:
            answer_preview = result['answer'][:100] + "..." if len(result['answer']) > 100 else result['answer']
            logger.info(f"   💬 Answer: {answer_preview}")

    # Persist diet plans / health queries for the signed-in patient so their
    # doctor can review them later (Doctor Dashboard → Diet Plans / Health
    # Queries). Best-effort — never fail the patient's request over this.
    if current_patient and not result.get("error"):
        db = get_db()
        try:
            if name == "generate_diet":
                db.create_diet_plan(current_patient.id, {
                    "preferences": result.get("preference"),
                    "daily_calories": result.get("daily_calories"),
                    "allergies": result.get("allergies"),
                    "plan_text": result.get("plan"),
                    "meals": result.get("meals"),
                    "source": "mistral_ai" if result.get("plan") else "template",
                })
            elif name == "general_query":
                db.create_health_query(
                    current_patient.id,
                    question=args.get("question"),
                    answer=result.get("answer"),
                    source=result.get("source"),
                )
        except Exception as e:
            logger.warning(f"⚠️  Failed to persist {name} history for patient {current_patient.id}: {e}")

    logger.info("=" * 80)
    logger.info("")

    return result

# ── Serve Frontend ──────────────────────────────────────────────────────
# Mount frontend static files (must be after API routes)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

@app.get("/")
def serve_frontend():
    """Serve the frontend index.html"""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/doctor-dashboard")
def serve_doctor_dashboard():
    """Serve the Doctor Dashboard SPA (separate page, same session/backend as the patient app)."""
    return FileResponse(os.path.join(FRONTEND_DIR, "doctor-dashboard.html"))

# Mount static assets from frontend/ at /assets (for future CSS/JS files)
if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="frontend-assets")
