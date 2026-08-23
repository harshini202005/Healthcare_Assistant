"""
Booking management tools for Healthcare MCP Server
Uses Supabase for persistent storage of appointments
"""

import logging
import random
import re
from datetime import datetime
from typing import Optional, Tuple
from backend.database import get_db
from backend.constants import (
    SLOT_INTERVAL_MINUTES,
    CLINIC_OPEN_HOUR,
    CLINIC_CLOSE_HOUR,
)

logger = logging.getLogger(__name__)


def validate_slot_interval(time_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that the time is in SLOT_INTERVAL_MINUTES intervals.

    Args:
        time_str: Time string in HH:MM format

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        hour, minute = map(int, time_str.split(":"))

        # Check if minutes align with the clinic's slot interval (e.g. 00, 20, 40)
        if minute % SLOT_INTERVAL_MINUTES != 0:
            valid_minutes = ", ".join(f"{m:02d}" for m in range(0, 60, SLOT_INTERVAL_MINUTES))
            return (
                False,
                f"Time must be in {SLOT_INTERVAL_MINUTES}-minute intervals ({valid_minutes}). Got: {minute}",
            )

        # Validate hour (0-23)
        if hour < 0 or hour > 23:
            return False, f"Hour must be between 00 and 23. Got: {hour}"

        return True, None
    except Exception as e:
        return False, f"Invalid time format. Expected HH:MM. Got: {time_str}"


def validate_date(date_str: str) -> Tuple[bool, Optional[str]]:
    """Validate date format (YYYY-MM-DD) and ensure it is not in the past."""
    try:
        appointment_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return False, f"Invalid date format. Expected YYYY-MM-DD. Got: {date_str}"

    today = datetime.now().date()
    if appointment_date < today:
        return (
            False,
            f"Cannot book an appointment in the past. Provided date: {date_str}, today is: {today.isoformat()}",
        )

    return True, None


def validate_business_hours(time_str: str) -> Tuple[bool, Optional[str]]:
    """Validate that the appointment is within business hours (09:00 – 17:00)."""
    try:
        hour, minute = map(int, time_str.split(":"))
    except Exception:
        return False, f"Invalid time format. Expected HH:MM. Got: {time_str}"

    total_minutes = hour * 60 + minute
    open_minutes = CLINIC_OPEN_HOUR * 60
    close_minutes = CLINIC_CLOSE_HOUR * 60
    if total_minutes < open_minutes:
        return False, f"Appointments are available from {CLINIC_OPEN_HOUR:02d}:00 AM. Please choose a later time."
    if total_minutes > close_minutes:
        return False, f"Appointments are available until {CLINIC_CLOSE_HOUR - 12:02d}:00 PM. Please choose an earlier time."

    return True, None


def check_conflicts(
    date: str, time: str, specialty: str, doctor_id: Optional[str] = None
) -> Optional[dict]:
    """
    Check if there's a conflict at the same date, time and specialty/doctor.

    Args:
        date: Appointment date (YYYY-MM-DD)
        time: Appointment time (HH:MM)
        specialty: Medical specialty
        doctor_id: Specific doctor ID (optional)

    Returns:
        Existing booking dict if conflict exists, None otherwise
    """
    db = get_db()

    if doctor_id:
        # Check if specific doctor has conflict
        return db.check_doctor_conflict(doctor_id, date, time)
    else:
        # Check if any doctor in this specialty is available
        available = db.get_available_doctors(specialty, date, time)
        if not available:
            return {"specialty": specialty, "date": date, "time": time}
        return None


def book(
    user_id: str,
    date: str,
    time: str,
    specialty: Optional[str] = None,
    reason: Optional[str] = None,
    doctor_id: Optional[str] = None,
    patient_display: Optional[str] = None,
) -> dict:
    """
    Book a medical appointment with conflict checking and slot-interval validation
    (SLOT_INTERVAL_MINUTES, currently 20 minutes). Now stores appointments in Supabase database.

    Args:
        user_id: Unique identifier for the patient (the authenticated patient's id)
        date: Appointment date (YYYY-MM-DD format)
        time: Appointment time in SLOT_INTERVAL_MINUTES intervals (HH:MM format)
        specialty: Medical specialty (e.g., 'Cardiology', 'Dermatology')
        reason: Reason for visit
        doctor_id: Preferred doctor ID (optional - auto-assigned if not provided)
        patient_display: Human-friendly patient label (e.g. email) shown in the
            confirmation instead of the raw id. Falls back to user_id.

    Returns:
        Confirmation details or error if validation fails or conflict exists
    """
    logger.debug(f"TOOL CALLED: book_appointment")
    logger.debug(f"Patient: {user_id}")
    logger.debug(f"Date: {date}")
    logger.debug(f"Time: {time}")
    logger.debug(f"Specialty: {specialty}")
    logger.debug(f"Reason: {reason}")
    logger.debug(f"Preferred Doctor: {doctor_id or 'Auto-assign'}")

    specialty_provided = bool(specialty)

    # Resolve a doctor name (e.g. extracted from chat: "Dr. Patel") into a real
    # doctor_id — only "doc_XXX" style values are treated as an actual ID.
    if doctor_id and not re.match(r"^doc[_-]?\d+$", doctor_id, re.IGNORECASE):
        db_lookup = get_db()
        matches = db_lookup.search_doctors(doctor_id)
        if matches:
            doctor_id = matches[0]["id"]
            if not specialty_provided:
                specialty = matches[0]["specialty"]
        # If no match, leave doctor_id as-is — the lookup below will report
        # "Doctor not found" with a helpful suggestion.

    # Set default specialty
    if not specialty:
        specialty = "General Practice"

    # Validate date format
    date_valid, date_error = validate_date(date)
    if not date_valid:
        logger.error(f"Invalid date: {date_error}")
        return {
            "error": True,
            "message": date_error,
            "suggestion": "Please provide date in YYYY-MM-DD format (e.g., 2026-01-19)",
        }

    # Validate time format and slot interval
    time_valid, time_error = validate_slot_interval(time)
    if not time_valid:
        logger.error(f"Invalid time: {time_error}")
        return {
            "error": True,
            "message": time_error,
            "suggestion": f"Available times: {CLINIC_OPEN_HOUR:02d}:00, {CLINIC_OPEN_HOUR:02d}:20, {CLINIC_OPEN_HOUR:02d}:40 … {CLINIC_CLOSE_HOUR - 1:02d}:40, {CLINIC_CLOSE_HOUR:02d}:00",
        }

    # Validate business hours
    hours_valid, hours_error = validate_business_hours(time)
    if not hours_valid:
        logger.error(f"Outside business hours: {hours_error}")
        return {
            "error": True,
            "message": hours_error,
            "suggestion": f"Clinic hours: Monday–Friday, {CLINIC_OPEN_HOUR:02d}:00 AM – {CLINIC_CLOSE_HOUR - 12:02d}:00 PM",
        }

    db = get_db()

    # If doctor_id provided, verify they exist and specialize in this area
    if doctor_id:
        doctor = db.get_doctor_by_id(doctor_id)
        if not doctor:
            return {
                "error": True,
                "message": f"Doctor not found: {doctor_id}",
                "suggestion": "Use get_doctors to find valid doctor IDs",
            }

        # Check if doctor specializes in requested specialty
        if doctor["specialty"].lower() != specialty.lower():
            return {
                "error": True,
                # doctor["name"] already includes a "Dr." prefix (e.g. "Dr. Sarah
                # Johnson") — don't add a second one.
                "message": f"{doctor['name']} specializes in {doctor['specialty']}, not {specialty}",
                "suggestion": f"Choose a {specialty} specialist or change specialty to {doctor['specialty']}",
            }

        # Check if doctor is available at this time
        conflict = db.check_doctor_conflict(doctor_id, date, time)
        if conflict:
            return {
                "error": True,
                "message": f"{doctor['name']} is already booked at {time} on {date}",
                "suggestion": "Use get_available_slots to find open times with this doctor",
            }

        assigned_doctor = doctor
    else:
        # Auto-assign an available doctor
        available_doctors = db.get_available_doctors(specialty, date, time)

        if not available_doctors:
            return {
                "error": True,
                "message": f"No {specialty} doctors available at {time} on {date}",
                "suggestion": "Use get_available_slots to find open appointment times",
            }

        # Pick first available doctor (could implement load balancing here)
        assigned_doctor = available_doctors[0]
        doctor_id = assigned_doctor["id"]

    # Generate confirmation number
    confirmation_number = f"APT-{random.randint(10000, 99999)}"

    # Create booking data. No approval step — the appointment is confirmed
    # immediately; the assigned doctor is just notified (see below) so their
    # dashboard bell lights up, but the patient doesn't wait on doctor action.
    booking_data = {
        "confirmation_number": confirmation_number,
        "patient_id": user_id,
        "doctor_id": doctor_id,
        "appointment_date": date,
        "appointment_time": time,
        "specialty": specialty,
        "reason": reason,
        "status": "confirmed",
    }

    # Save to Supabase. This used to silently fall back to writing a local
    # bookings.json file on failure and then report success anyway — that file
    # was never read back by anything (not conflict checks, not the patient's
    # own history, not the doctor's dashboard), so the appointment would
    # effectively vanish while the patient was told it was booked. Report the
    # failure instead so the patient knows to retry.
    try:
        created_appointment = db.create_appointment(booking_data)
        logger.info(f"Appointment saved to database")
    except Exception as e:
        logger.error(f"Failed to save appointment to database: {e}")
        return {
            "error": True,
            "message": "We couldn't save your appointment due to a system error. Please try again.",
            "suggestion": "If this keeps happening, contact support — no appointment was booked.",
        }

    # Notify the assigned doctor — this is what lights up their dashboard bell.
    # Informational only; no doctor action is required for the booking to stand.
    try:
        friendly_date, friendly_time = _friendly_date_time(date, time)
        patient_label = patient_display or user_id
        db.create_notification(
            doctor_id=doctor_id,
            type="new_appointment",
            title="New appointment booked",
            message=f"New appointment booked by {patient_label} for {friendly_date} at {friendly_time}.",
            appointment_id=created_appointment.get("id"),
        )
    except Exception as e:
        logger.warning(f"Failed to create doctor notification: {e}")

    logger.info(f"Appointment booked successfully")
    logger.debug(f"Confirmation: {confirmation_number}")
    logger.debug(f"Assigned Doctor: {assigned_doctor['name']}")

    return {
        "message": f"Appointment successfully booked with {assigned_doctor['name']}!",
        "confirmation_number": confirmation_number,
        "details": {
            "Patient": patient_display or user_id,
            "Doctor": assigned_doctor["name"],
            "Doctor ID": doctor_id,
            "Date": date,
            "Time": time,
            "Specialty": specialty,
            "Reason": reason or "General checkup",
            "Status": "Confirmed",
        },
        "instructions": [
            "📝 Please arrive 15 minutes early",
            "🪪 Bring your insurance card and ID",
            "📞 To cancel or reschedule, contact us 24 hours in advance",
        ],
    }


def _friendly_date_time(date: str, time: str) -> Tuple[str, str]:
    """
    Format 'YYYY-MM-DD' / 'HH:MM' as ('August 25, 2026', '10:30 AM') for
    human-readable notification text. Avoids the '%-d'/'%-I' strftime flags
    (glibc-only, not supported on Windows) by trimming the padded zero manually.
    """
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        friendly_date = f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except ValueError:
        friendly_date = date
    try:
        tm = datetime.strptime(time[:5], "%H:%M")
        hour_12 = tm.strftime("%I").lstrip("0") or "12"
        friendly_time = f"{hour_12}:{tm.strftime('%M %p')}"
    except ValueError:
        friendly_time = time
    return friendly_date, friendly_time


def get_appointment(confirmation_number: str) -> dict:
    """
    Retrieve appointment details by confirmation number

    Args:
        confirmation_number: The confirmation number from booking

    Returns:
        Appointment details or error if not found
    """
    logger.debug(f"TOOL CALLED: get_appointment")
    logger.debug(f"Confirmation: {confirmation_number}")

    db = get_db()

    try:
        response = (
            db.client.table("appointments")
            .select("*, doctors(*)")
            .eq("confirmation_number", confirmation_number)
            .single()
            .execute()
        )

        if not response.data:
            return {
                "error": True,
                "message": f"Appointment not found: {confirmation_number}",
                "suggestion": "Check your confirmation number and try again",
            }

        appt = response.data

        return {
            "message": "Appointment found",
            "appointment": {
                "confirmation_number": appt["confirmation_number"],
                "status": appt["status"],
                "patient_id": appt["patient_id"],
                "date": appt["appointment_date"],
                "time": appt["appointment_time"],
                "specialty": appt["specialty"],
                "reason": appt.get("reason", "Not specified"),
                "doctor": {
                    "name": appt.get("doctors", {}).get("name", "Unknown"),
                    "specialty": appt.get("doctors", {}).get("specialty", "Unknown"),
                },
                "booked_at": appt.get("booked_at"),
            },
        }

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"error": True, "message": f"Failed to retrieve appointment: {str(e)}"}


def cancel_appointment(confirmation_number: str, reason: Optional[str] = None) -> dict:
    """
    Cancel an existing appointment

    Args:
        confirmation_number: The confirmation number
        reason: Optional cancellation reason

    Returns:
        Cancellation confirmation
    """
    logger.debug(f"TOOL CALLED: cancel_appointment")
    logger.debug(f"Confirmation: {confirmation_number}")

    db = get_db()

    try:
        # First get the appointment
        response = (
            db.client.table("appointments")
            .select("*")
            .eq("confirmation_number", confirmation_number)
            .single()
            .execute()
        )

        if not response.data:
            return {
                "error": True,
                "message": f"Appointment not found: {confirmation_number}",
            }

        appt = response.data

        # Update status to cancelled
        db.client.table("appointments").update(
            {"status": "cancelled", "notes": reason or "Cancelled by patient"}
        ).eq("confirmation_number", confirmation_number).execute()

        logger.info(f"Appointment cancelled")

        # Notify the doctor — a patient cancelling their own appointment is one
        # of the notification types the doctor dashboard bell supports.
        try:
            if appt.get("doctor_id"):
                patient = db.get_patient(appt["patient_id"]) if appt.get("patient_id") else None
                patient_label = (patient or {}).get("full_name") or (patient or {}).get("email") or "A patient"
                friendly_date, friendly_time = _friendly_date_time(appt["appointment_date"], appt["appointment_time"][:5])
                db.create_notification(
                    doctor_id=appt["doctor_id"],
                    type="appointment_cancelled",
                    title="Appointment cancelled",
                    message=f"{patient_label} cancelled their appointment on {friendly_date} at {friendly_time}.",
                    appointment_id=appt.get("id"),
                )
        except Exception as e:
            logger.warning(f"Failed to create cancellation notification: {e}")

        return {
            "message": "Appointment successfully cancelled",
            "confirmation_number": confirmation_number,
            "refund_policy": "Refund will be processed within 5-7 business days",
        }

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"error": True, "message": f"Failed to cancel appointment: {str(e)}"}