"""
Doctor management tools for Healthcare MCP Server
Handles doctor queries, availability checks, and slot generation
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from backend.database import get_db
from backend.constants import (
    SLOT_INTERVAL_MINUTES,
    SLOT_MINUTE_MARKS,
    CLINIC_OPEN_HOUR,
    CLINIC_CLOSE_HOUR,
)

logger = logging.getLogger(__name__)


def get_doctors(specialty: Optional[str] = None) -> Dict[str, Any]:
    """
    Get list of doctors, optionally filtered by specialty
    
    Args:
        specialty: Medical specialty to filter by (e.g., 'cardiology', 'dermatology')
    
    Returns:
        List of doctors with their details
    """
    logger.debug(f"TOOL CALLED: get_doctors")
    logger.debug(f"Specialty: {specialty or 'All'}")
    
    db = get_db()
    
    try:
        doctors = db.get_doctors(specialty)
        
        if not doctors:
            return {
                "message": f"No doctors found{f' for specialty: {specialty}' if specialty else ''}",
                "doctors": [],
                "suggestion": "Try searching for a different specialty"
            }
        
        # Format response
        formatted_doctors = []
        specialties_found = set()
        
        for doc in doctors:
            specialties_found.add(doc.get("specialty", "").title())
            formatted_doctors.append({
                "id": doc["id"],
                "name": doc["name"],
                "specialty": doc["specialty"].title(),
                "experience": f"{doc.get('years_experience', 'N/A')} years",
                "email": doc.get("email", "N/A")
            })
        
        logger.info(f"Found {len(doctors)} doctors")
        
        return {
            "message": f"Found {len(doctors)} doctor(s)",
            "specialties_available": list(specialties_found),
            "doctors": formatted_doctors,
            "instruction": "Use get_available_slots to check when these doctors are available"
        }
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            "error": True,
            "message": f"Failed to fetch doctors: {str(e)}",
            "doctors": []
        }


def get_available_slots(specialty: str, date: str, doctor_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get available appointment slots for a specific date and specialty
    
    Args:
        specialty: Medical specialty required
        date: Date to check (YYYY-MM-DD format)
        doctor_id: Specific doctor ID (optional - if not provided, checks all doctors in specialty)
    
    Returns:
        Available time slots with doctor assignments
    """
    logger.debug(f"TOOL CALLED: get_available_slots")
    logger.debug(f"Specialty: {specialty}")
    logger.debug(f"Date: {date}")
    logger.debug(f"Doctor ID: {doctor_id or 'Any'}")
    
    # Validate date format
    try:
        check_date = datetime.strptime(date, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        if check_date < today:
            return {
                "error": True,
                "message": f"Cannot check availability for past date: {date}",
                "suggestion": "Please provide a future date"
            }
            
        weekday = check_date.weekday()  # 0=Monday
        
        # Weekend check (Saturday=5, Sunday=6)
        if weekday >= 5:
            return {
                "message": "Clinic is closed on weekends",
                "available_slots": [],
                "suggestion": "Please choose a weekday (Monday-Friday)"
            }
            
    except ValueError:
        return {
            "error": True,
            "message": f"Invalid date format: {date}",
            "suggestion": "Use YYYY-MM-DD format (e.g., 2026-01-25)"
        }
    
    db = get_db()
    
    try:
        # If specific doctor requested, verify they exist
        target_doctors = []
        if doctor_id:
            doctor = db.get_doctor_by_id(doctor_id)
            if not doctor:
                return {
                    "error": True,
                    "message": f"Doctor not found: {doctor_id}",
                    "suggestion": "Use get_doctors to find valid doctor IDs"
                }
            if doctor["specialty"].lower() != specialty.lower():
                return {
                    "error": True,
                    "message": f"Doctor {doctor['name']} specializes in {doctor['specialty']}, not {specialty}",
                    "suggestion": "Choose a doctor matching your required specialty"
                }
            target_doctors = [doctor]
        else:
            # Get all doctors for this specialty
            target_doctors = db.get_doctors(specialty)
            
        if not target_doctors:
            return {
                "message": f"No doctors available for {specialty}",
                "available_slots": [],
                "suggestion": "Try a different specialty or date"
            }
        
        # Generate the clinic day's slot times, e.g. 09:00, 09:20, ... 16:40
        slot_times = []
        for hour in range(CLINIC_OPEN_HOUR, CLINIC_CLOSE_HOUR):
            for minute in SLOT_MINUTE_MARKS:
                slot_times.append(f"{hour:02d}:{minute:02d}")

        total_slots_per_doctor = len(slot_times)
        available_slots = []
        occupied_slots = []
        queue = {}

        # One query per doctor (not one per slot-per-doctor) to build both the
        # free-slot list and a real "how busy is this doctor today" queue view.
        for doctor in target_doctors:
            booked_appointments = db.get_doctor_appointments(doctor["id"], date)
            # Supabase returns appointment_time as "HH:MM:SS" — normalize to
            # "HH:MM" so it matches the generated slot_times strings.
            booked_times = {appt["appointment_time"][:5] for appt in booked_appointments}

            for slot_time in slot_times:
                entry = {
                    "time": slot_time,
                    "doctor_id": doctor["id"],
                    "doctor_name": doctor["name"],
                    "specialty": doctor["specialty"].title()
                }
                (occupied_slots if slot_time in booked_times else available_slots).append(entry)

            booked_count = len(booked_times)
            booked_ratio = (booked_count / total_slots_per_doctor) if total_slots_per_doctor else 0
            if booked_ratio >= 0.7:
                load = "busy"
            elif booked_ratio >= 0.35:
                load = "moderate"
            else:
                load = "low"

            queue[doctor["id"]] = {
                "doctor_name": doctor["name"],
                "booked_today": booked_count,
                "total_slots": total_slots_per_doctor,
                "load": load,
                "estimated_wait_minutes": booked_count * SLOT_INTERVAL_MINUTES
            }

        if not available_slots:
            return {
                "message": f"No available slots for {specialty} on {date}",
                "available_slots": [],
                "occupied_slots": occupied_slots,
                "queue": queue,
                "suggestion": "Try a different date or check if doctors have availability overrides"
            }

        # Group by time slot for better readability
        slots_by_time = {}
        for slot in available_slots:
            slots_by_time.setdefault(slot["time"], []).append({
                "doctor_id": slot["doctor_id"],
                "doctor_name": slot["doctor_name"]
            })

        occupied_by_time = {}
        for slot in occupied_slots:
            occupied_by_time.setdefault(slot["time"], []).append({
                "doctor_id": slot["doctor_id"],
                "doctor_name": slot["doctor_name"]
            })

        logger.info(f"Found {len(available_slots)} available slots")

        return {
            "message": f"Found {len(slots_by_time)} available time slots for {specialty}",
            "date": date,
            "specialty": specialty.title(),
            "available_slots": slots_by_time,
            "occupied_slots": occupied_by_time,
            "queue": queue,
            "total_options": len(available_slots),
            "instruction": "Use book_appointment with doctor_id to book a specific slot"
        }
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            "error": True,
            "message": f"Failed to get available slots: {str(e)}",
            "available_slots": []
        }


def get_doctor_schedule(doctor_identifier: str) -> Dict[str, Any]:
    """
    Get weekly schedule for a specific doctor
    
    Args:
        doctor_identifier: Doctor's unique ID (e.g., 'doc_001') or name (e.g., 'Priya Patel')
    
    Returns:
        Weekly schedule with working hours
    """
    logger.debug(f"TOOL CALLED: get_doctor_schedule")
    logger.debug(f"Identifier: {doctor_identifier}")
    
    db = get_db()
    
    try:
        # Try to find doctor by ID first, then by name
        doctor = None
        
        if doctor_identifier.startswith('doc_'):
            # Looks like an ID
            doctor = db.get_doctor_by_id(doctor_identifier)
        
        if not doctor:
            # Try searching by name
            search_results = db.search_doctors(doctor_identifier)
            if search_results:
                doctor = search_results[0]
                logger.info(f"Found doctor by name: {doctor['name']} ({doctor['id']})")
        
        if not doctor:
            return {
                "error": True,
                "message": f"Doctor not found: '{doctor_identifier}'",
                "suggestion": "Use get_doctors to see all available doctors, or provide the doctor ID (e.g., doc_001) or full/partial name (e.g., 'Priya Patel')"
            }
        
        # Use the actual doctor ID for schedule lookup
        actual_doctor_id = doctor['id']
        schedules = db.get_doctor_schedule(actual_doctor_id)
        
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        formatted_schedule = []
        
        for sched in schedules:
            day_idx = sched.get("day_of_week", 0)
            if sched.get("is_available"):
                formatted_schedule.append({
                    "day": days[day_idx],
                    "hours": f"{sched['start_time']} - {sched['end_time']}"
                })
        
        return {
            "message": f"Weekly schedule for {doctor['name']}",
            "doctor": {
                "id": doctor["id"],
                "name": doctor["name"],
                "specialty": doctor["specialty"].title()
            },
            "schedule": formatted_schedule
        }
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            "error": True,
            "message": f"Failed to get schedule: {str(e)}"
        }