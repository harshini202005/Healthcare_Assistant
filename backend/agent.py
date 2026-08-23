"""
Healthcare chat agent: a Mistral tool-calling loop over the existing MCP
tool registry (backend/mcp.py), replacing the frontend's regex-based intent
router with a real conversational agent.

Design notes (see project memory / conversation for the fuller rationale):
- Booking/cancelling is never executed on the model's first tool call. The
  first call is intercepted and turned into a "confirmation_required" result
  so the model has to describe the action and ask the patient to confirm.
  Only an explicit affirmative reply on the *next* turn actually executes it
  (see _execute_confirmed_action). This is a code-enforced gate, not just a
  prompt instruction — the model cannot bypass it by calling the tool twice.
- user_id for book_appointment and ownership for cancel_appointment are
  always re-derived from the authenticated session at execution time, never
  taken from model-provided args — same rule /mcp/call already follows for
  the same reason (a chat message is client-controlled text).
- History is in-memory only, keyed by a client-supplied session_id. Lost on
  server restart; fine for now, see conversation for the persistence tradeoff.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from mistralai import Mistral

from backend.auth import CurrentPatient
from backend.database import get_db
from backend.mcp import call_tool, tools as MCP_TOOLS

logger = logging.getLogger(__name__)

AGENT_MODEL = os.getenv("MISTRAL_AGENT_MODEL", "mistral-small-latest")
MAX_TOOL_ROUNDS = 5          # hard cap on tool-call ping-pong per patient turn
MAX_HISTORY_MESSAGES = 40    # trimmed at user-turn boundaries, see _trim_history

# Tools that commit a real side effect and therefore go through the
# confirm-then-execute gate instead of running on the model's first call.
CONFIRMABLE_TOOLS = {"book_appointment", "cancel_appointment"}

SYSTEM_PROMPT = """You are the Healthcare assistant for patients, orchestrating tools to help with health questions, diet plans, and appointment booking.

TOOLS:
- Use get_doctors / get_available_slots / get_doctor_schedule / get_appointment to look things up.
- Use generate_diet for any diet/meal plan request instead of writing one yourself.
- Use general_query for ANY medical, symptom, treatment, nutrition, fitness, or mental-health question instead of answering from your own knowledge — that tool has vetted medical safety rules and will refuse anything out of scope. Never answer a health question directly yourself.
- Use book_appointment / cancel_appointment when the patient wants to book or cancel. Before you have all required info (specialty or doctor, date, time for booking; confirmation number for cancelling), ask the patient for what's missing instead of guessing.

CONFIRMATION RULE (must follow exactly):
- The first time you call book_appointment or cancel_appointment in a conversation, it will NOT actually execute — you will get back a "confirmation_required" result. When that happens, clearly describe the exact action to the patient (doctor/specialty, date, time, or which appointment is being cancelled) and ask them to explicitly reply yes or no. Do not call that tool again yourself — the system executes it automatically once the patient confirms in their next message.
- If a tool result says "authentication_required", tell the patient they need to sign in before you can do that, and don't attempt the action again this turn.

STYLE: Be concise and warm. Never diagnose. Never invent doctor names, slots, or confirmation numbers — only use what tools actually returned."""


def _system_message() -> Dict[str, str]:
    """
    Build the system message fresh per request, with today's real date
    injected. Without this, the model has no way to know the actual current
    date and guesses a year from its own training data when the patient
    gives a partial date (e.g. "August 25" with no year) — which then fails
    booking's past-date check if the guessed year has already passed.
    """
    today = datetime.now().date()
    return {
        "role": "system",
        "content": (
            f"{SYSTEM_PROMPT}\n\n"
            f"Today's date is {today.isoformat()} ({today.strftime('%A, %B %d, %Y')}). "
            "Resolve relative dates (\"tomorrow\", \"next Monday\") and dates the patient "
            "gives without a year (e.g. \"August 25\") against this date — always assume "
            "the nearest upcoming occurrence, never a year from your own training data."
        ),
    }

_AFFIRM_RE = re.compile(
    r"^\s*(?:y|yes|yeah|yep|yup|sure|confirm(?:ed)?|ok(?:ay)?|go ahead|do it|"
    r"please (?:do|book|cancel) it|book it|cancel it|proceed|sounds good)\b",
    re.I,
)
_DECLINE_RE = re.compile(
    r"^\s*(?:n|no|nope|nah|don'?t|do not|cancel that|never\s*mind|nevermind|stop|wait|actually no)\b",
    re.I,
)


def _is_affirmative(text: str) -> bool:
    return bool(_AFFIRM_RE.match((text or "").strip()))


def _is_negative(text: str) -> bool:
    return bool(_DECLINE_RE.match((text or "").strip()))


def _to_mistral_tools() -> List[Dict[str, Any]]:
    """Convert the MCP tool registry's schemas into Mistral's function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"],
            },
        }
        for t in MCP_TOOLS.values()
    ]


_MISTRAL_TOOLS = _to_mistral_tools()

# session_id -> {"messages": [...], "pending_action": Optional[{"tool", "args"}]}
# In-memory by design (see module docstring) — one process, lost on restart.
_sessions: Dict[str, Dict[str, Any]] = {}


def _get_session(session_id: str) -> Dict[str, Any]:
    return _sessions.setdefault(session_id, {"messages": [], "pending_action": None})


def _trim_history(messages: List[Dict[str, Any]], max_messages: int = MAX_HISTORY_MESSAGES) -> List[Dict[str, Any]]:
    """
    Drop the oldest complete conversational turns once history grows too large.
    Only cuts at user-message boundaries so an assistant tool_calls message is
    never separated from the tool results that answer it (the API rejects that
    sequence).
    """
    if len(messages) <= max_messages:
        return messages
    user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    while len(messages) > max_messages and len(user_idxs) > 1:
        cutoff = user_idxs[1]
        messages = messages[cutoff:]
        user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    return messages


def _tool_call_args(tc) -> Dict[str, Any]:
    """FunctionCall.arguments is typed as Union[dict, str] by the SDK — handle both."""
    raw = tc.function.arguments
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _tool_call_to_history(tc) -> Dict[str, Any]:
    """Serialize a ToolCall response object back into the plain-dict shape the
    SDK's message TypedDicts expect, so it can be replayed in the next request."""
    raw = tc.function.arguments
    arguments = raw if isinstance(raw, str) else json.dumps(raw or {})
    return {
        "id": tc.id,
        "type": "function",
        "function": {"name": tc.function.name, "arguments": arguments},
    }


def _execute_confirmed_action(tool: str, args: Dict[str, Any], current_patient: Optional[CurrentPatient]) -> Dict[str, Any]:
    """
    Actually perform book_appointment/cancel_appointment after the patient has
    confirmed. Identity and ownership are re-derived fresh here — never trusted
    from the proposal step or from model-provided args.
    """
    if current_patient is None:
        return {"error": True, "message": "You need to sign in before I can do that."}

    if tool == "book_appointment":
        safe_args = dict(args)
        safe_args["user_id"] = current_patient.id
        safe_args["patient_display"] = current_patient.email
        return call_tool("book_appointment", safe_args)

    if tool == "cancel_appointment":
        confirmation_number = args.get("confirmation_number")
        db = get_db()
        appt = db.get_appointment_by_confirmation(confirmation_number) if confirmation_number else None
        if not appt or appt.get("patient_id") != current_patient.id:
            return {"error": True, "message": "You can only cancel your own appointments."}
        return call_tool("cancel_appointment", args)

    return {"error": True, "message": f"Unknown confirmable action: {tool}"}


def run_agent_turn(session_id: str, user_message: str, current_patient: Optional[CurrentPatient]) -> Dict[str, Any]:
    """
    Advance one patient message through the agent loop and return:
      {
        "reply": str,
        "awaiting_confirmation": bool,   # true if a booking/cancel is now waiting on the patient's next reply
        "requires_auth": bool,           # true if this turn was blocked because the patient isn't signed in
        "executed_action": None | {"tool": str, "result": dict},  # a booking/cancel that actually ran this turn
      }
    """
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key or api_key == "your-mistral-api-key-here":
        return {
            "reply": "The assistant isn't configured yet — please ask an administrator to set MISTRAL_API_KEY.",
            "awaiting_confirmation": False,
            "requires_auth": False,
            "executed_action": None,
        }

    session = _get_session(session_id)
    executed_action: Optional[Dict[str, Any]] = None
    requires_auth = False

    # ── Resolve a pending confirmation left over from the previous turn ──
    pending = session.get("pending_action")
    if pending:
        session["pending_action"] = None
        if _is_affirmative(user_message):
            result = _execute_confirmed_action(pending["tool"], pending["args"], current_patient)
            executed_action = {"tool": pending["tool"], "result": result}
            session["messages"].append({
                "role": "system",
                "content": (
                    f"[The pending {pending['tool']} was just executed because the patient confirmed. "
                    f"Result: {json.dumps(result, default=str)}. Tell the patient the outcome in plain language.]"
                ),
            })
        elif _is_negative(user_message):
            session["messages"].append({
                "role": "system",
                "content": (
                    f"[The patient declined the pending {pending['tool']}. It was NOT executed. "
                    "Acknowledge that and ask what they'd like to do instead.]"
                ),
            })
        # Ambiguous reply: silently drop the pending action and treat the
        # message as a fresh request instead of blocking on it.

    session["messages"].append({"role": "user", "content": user_message})

    client = Mistral(api_key=api_key)
    reply_text: Optional[str] = None

    for _ in range(MAX_TOOL_ROUNDS):
        messages = [_system_message()] + session["messages"]
        try:
            response = client.chat.complete(
                model=AGENT_MODEL,
                messages=messages,
                tools=_MISTRAL_TOOLS,
                tool_choice="auto",
            )
        except Exception as e:
            logger.error(f"Agent loop: Mistral call failed: {e}")
            reply_text = "Sorry, I'm having trouble reaching the assistant service right now. Please try again shortly."
            break

        choice = response.choices[0].message
        tool_calls = choice.tool_calls

        if not tool_calls:
            reply_text = choice.content or "Sorry, I didn't catch that — could you rephrase?"
            session["messages"].append({"role": "assistant", "content": reply_text})
            break

        session["messages"].append({
            "role": "assistant",
            "content": choice.content or "",
            "tool_calls": [_tool_call_to_history(tc) for tc in tool_calls],
        })

        for tc in tool_calls:
            name = tc.function.name
            args = _tool_call_args(tc)

            if name in CONFIRMABLE_TOOLS:
                if current_patient is None:
                    requires_auth = True
                    tool_result = {
                        "status": "authentication_required",
                        "message": "The patient is not signed in. Tell them they need to sign in before you can book or cancel appointments.",
                    }
                else:
                    session["pending_action"] = {"tool": name, "args": args}
                    tool_result = {
                        "status": "confirmation_required",
                        "message": (
                            "Do NOT call this tool again. Describe this exact proposed action to the "
                            "patient in plain language and ask them to reply yes or no to confirm."
                        ),
                        "proposed": args,
                    }
            else:
                tool_result = call_tool(name, args)

            session["messages"].append({
                "role": "tool",
                "name": name,
                "tool_call_id": tc.id,
                "content": json.dumps(tool_result, default=str),
            })

    if reply_text is None:
        reply_text = "I'm not able to finish that request right now — could you try rephrasing or asking again?"

    session["messages"] = _trim_history(session["messages"])

    return {
        "reply": reply_text,
        "awaiting_confirmation": session.get("pending_action") is not None,
        "requires_auth": requires_auth,
        "executed_action": executed_action,
    }
