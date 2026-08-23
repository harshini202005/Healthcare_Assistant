"""
Healthcare MCP (Model Context Protocol) Server
Provides tools for diet planning, appointment booking, doctor management, and health queries.
"""

from typing import Dict, Any, List, Optional
from backend.tools import diet, booking, general, doctors


# MCP Tool Registry with detailed schemas
tools = {
    "generate_diet": {
        "name": "generate_diet",
        "description": "Generate personalized AI-powered diet plans based on user preferences and health goals",
        "inputSchema": {
            "type": "object",
            "properties": {
                "preferences": {
                    "type": "string",
                    "description": "Dietary preferences (e.g., 'vegetarian', 'low-carb', 'diabetic-friendly')"
                },
                "calories": {
                    "type": "integer",
                    "description": "Target daily calorie intake"
                },
                "allergies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of food allergies or restrictions"
                }
            },
            "required": ["preferences"]
        }
    },
    "book_appointment": {
        "name": "book_appointment",
        "description": "Book medical appointments with healthcare providers. Appointments are scheduled in 20-minute intervals. Auto-assigns available doctor if none specified.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Unique identifier for the patient"
                },
                "date": {
                    "type": "string",
                    "description": "Appointment date (YYYY-MM-DD format)"
                },
                "time": {
                    "type": "string",
                    "description": "Appointment time in 20-minute intervals (HH:MM format, e.g., '09:00', '09:20', '09:40')"
                },
                "specialty": {
                    "type": "string",
                    "description": "Medical specialty (e.g., 'cardiology', 'dermatology', 'general practice')"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for visit"
                },
                "doctor_id": {
                    "type": "string",
                    "description": "Preferred doctor ID (optional - will auto-assign if not provided)"
                }
            },
            "required": ["user_id", "date", "time"],
            "note": "user_id is derived server-side from the caller's Supabase Auth session and cannot be spoofed by the client."
        }
    },
    "get_doctors": {
        "name": "get_doctors",
        "description": "Get list of doctors filtered by specialty. Use this before booking to see available doctors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Medical specialty to filter by (e.g., 'cardiology', 'dermatology', 'pediatrics'). Omit to get all doctors."
                }
            },
            "required": []
        }
    },
    "get_available_slots": {
        "name": "get_available_slots",
        "description": "Get available appointment slots for a specific date and specialty. Shows which doctors are free at each time slot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": "Required medical specialty (e.g., 'cardiology', 'dermatology')"
                },
                "date": {
                    "type": "string",
                    "description": "Date to check availability (YYYY-MM-DD format)"
                },
                "doctor_id": {
                    "type": "string",
                    "description": "Specific doctor ID to check (optional - checks all doctors in specialty if not provided)"
                }
            },
            "required": ["specialty", "date"]
        }
    },
    "get_doctor_schedule": {
        "name": "get_doctor_schedule",
        "description": "Get weekly working schedule for a specific doctor. Accepts doctor ID (doc_001) or name (Priya Patel).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doctor_id": {
                    "type": "string",
                    "description": "Doctor's unique ID (e.g., 'doc_001') or name (e.g., 'Priya Patel', 'Dr. Sarah Johnson')"
                }
            },
            "required": ["doctor_id"]
        }
    },
    "get_appointment": {
        "name": "get_appointment",
        "description": "Retrieve appointment details using confirmation number",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirmation_number": {
                    "type": "string",
                    "description": "Confirmation number from booking (e.g., 'APT-12345')"
                }
            },
            "required": ["confirmation_number"]
        }
    },
    "cancel_appointment": {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirmation_number": {
                    "type": "string",
                    "description": "Confirmation number of the appointment to cancel"
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for cancellation"
                }
            },
            "required": ["confirmation_number"]
        }
    },
    "general_query": {
        "name": "general_query",
        "description": "Answer general health and wellness questions with evidence-based information",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Health-related question to answer"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context or patient information (optional)"
                }
            },
            "required": ["question"]
        }
    }
}


def get_available_tools() -> List[Dict[str, Any]]:
    """
    Return list of all available MCP tools with their schemas.
    
    Returns:
        List of tool definitions compatible with MCP protocol
    """
    return list(tools.values())


def call_tool(name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute a tool by name with provided arguments.
    
    Args:
        name: Name of the tool to execute
        args: Dictionary of arguments for the tool
        
    Returns:
        Tool execution result or error message
        
    Raises:
        ValueError: If tool name is unknown or required arguments are missing
    """
    if args is None:
        args = {}
    
    # Validate tool exists
    if name not in tools:
        return {
            "error": f"Unknown tool: {name}",
            "available_tools": list(tools.keys())
        }
    
    try:
        # Route to appropriate tool handler
        if name == "generate_diet":
            preferences = args.get("preferences")
            if not preferences:
                return {"error": "Missing required parameter: preferences"}
            
            return diet.generate(
                preferences=preferences,
                calories=args.get("calories"),
                allergies=args.get("allergies", [])
            )
            
        elif name == "book_appointment":
            user_id = args.get("user_id")
            date = args.get("date")
            time = args.get("time")
            
            if not user_id or not date or not time:
                return {"error": "Missing required parameters: user_id, date, and time"}
            
            return booking.book(
                user_id=user_id,
                date=date,
                time=time,
                specialty=args.get("specialty"),
                reason=args.get("reason"),
                doctor_id=args.get("doctor_id"),
                patient_display=args.get("patient_display")
            )

        elif name == "get_doctors":
            return doctors.get_doctors(
                specialty=args.get("specialty")
            )

        elif name == "get_available_slots":
            specialty = args.get("specialty")
            date = args.get("date")
            
            if not specialty or not date:
                return {"error": "Missing required parameters: specialty and date"}
            
            return doctors.get_available_slots(
                specialty=specialty,
                date=date,
                doctor_id=args.get("doctor_id")
            )

        elif name == "get_doctor_schedule":
            doctor_id = args.get("doctor_id")
            if not doctor_id:
                return {"error": "Missing required parameter: doctor_id"}
            
            return doctors.get_doctor_schedule(doctor_identifier=doctor_id)

        elif name == "get_appointment":
            confirmation_number = args.get("confirmation_number")
            if not confirmation_number:
                return {"error": "Missing required parameter: confirmation_number"}
            
            return booking.get_appointment(confirmation_number=confirmation_number)

        elif name == "cancel_appointment":
            confirmation_number = args.get("confirmation_number")
            if not confirmation_number:
                return {"error": "Missing required parameter: confirmation_number"}
            
            return booking.cancel_appointment(
                confirmation_number=confirmation_number,
                reason=args.get("reason")
            )
            
        elif name == "general_query":
            question = args.get("question")
            if not question:
                return {"error": "Missing required parameter: question"}
            
            return general.answer(
                question=question,
                context=args.get("context")
            )
            
    except Exception as e:
        return {
            "error": f"Tool execution failed: {str(e)}",
            "tool": name
        }
    
    return {"error": "Tool handler not implemented"}


def validate_tool_args(tool_name: str, args: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate arguments against tool schema.
    
    Args:
        tool_name: Name of the tool
        args: Arguments to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if tool_name not in tools:
        return False, f"Unknown tool: {tool_name}"
    
    tool_schema = tools[tool_name]["inputSchema"]
    required_fields = tool_schema.get("required", [])
    
    for field in required_fields:
        if field not in args or args[field] is None:
            return False, f"Missing required field: {field}"
    
    return True, None