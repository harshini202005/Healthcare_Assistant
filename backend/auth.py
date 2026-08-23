"""
Authentication helpers for the Healthcare API.

Uses Supabase Auth (GoTrue) for signup/login and JWT verification, so a
patient's identity comes from a verified token instead of a client-supplied
"Patient ID" string.

IMPORTANT: auth operations create a throwaway Supabase client instead of
reusing the shared `db.client` singleton from backend/database.py. Signing
in / verifying a user's token mutates a client's internal session state —
reusing the shared, service-role-keyed singleton would leak one patient's
session into the process-wide client used for every other database call
(a real bug in a concurrent server, not a theoretical one).
"""

import os
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException
from supabase import create_client, Client

from backend.database import get_db


def new_auth_client() -> Client:
    """Create a fresh Supabase client scoped to a single auth operation."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in environment")
    return create_client(url, key)


def new_admin_client() -> Client:
    """
    Create a Supabase client authenticated with the service_role key, needed for
    Auth Admin API calls (e.g. admin.create_user) that the anon key can't perform.
    """
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment")
    return create_client(url, service_key)


@dataclass
class CurrentPatient:
    id: str
    email: str


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Please sign in.",
        )
    return authorization.split(" ", 1)[1].strip()


def get_current_patient(authorization: Optional[str] = Header(None)) -> CurrentPatient:
    """
    FastAPI dependency: verifies the bearer token against Supabase Auth and
    returns the patient's identity. Raises 401 if missing/invalid/expired.
    """
    token = _extract_token(authorization)
    client = new_auth_client()

    try:
        response = client.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")

    if not response or not response.user:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")

    return CurrentPatient(id=response.user.id, email=response.user.email)


def get_current_patient_optional(authorization: Optional[str] = Header(None)) -> Optional[CurrentPatient]:
    """Same as get_current_patient, but returns None instead of raising when not authenticated."""
    if not authorization:
        return None
    try:
        return get_current_patient(authorization)
    except HTTPException:
        return None


@dataclass
class CurrentDoctor:
    id: str          # Supabase Auth user id
    doctor_id: str    # doctors.id (e.g. "doc_001")
    name: str
    specialty: str


def get_current_doctor(authorization: Optional[str] = Header(None)) -> CurrentDoctor:
    """
    FastAPI dependency: verifies the bearer token the same way get_current_patient
    does, then requires it to belong to a provisioned doctor account (a doctors row
    with a matching auth_user_id) — this is what stops a patient's token from
    reaching doctor-only endpoints. Raises 401 if not authenticated, 403 if
    authenticated but not a doctor.
    """
    token = _extract_token(authorization)
    client = new_auth_client()

    try:
        response = client.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")

    if not response or not response.user:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")

    db = get_db()
    doctor = db.get_doctor_by_auth_user_id(response.user.id)
    if not doctor:
        raise HTTPException(status_code=403, detail="This account is not registered as a doctor.")

    return CurrentDoctor(
        id=response.user.id,
        doctor_id=doctor["id"],
        name=doctor["name"],
        specialty=doctor["specialty"],
    )
