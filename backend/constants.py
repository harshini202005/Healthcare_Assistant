"""
Shared scheduling constants for the Healthcare MCP Server.
Single source of truth so slot generation (doctors.py) and booking
validation (booking.py) can never drift out of sync again.
"""

SLOT_INTERVAL_MINUTES = 20  # real-world OPD-style slot granularity
CLINIC_OPEN_HOUR = 9        # 09:00
CLINIC_CLOSE_HOUR = 17      # 17:00 (last bookable slot starts at 16:40)

# Minute marks within an hour that a slot can start on, e.g. [0, 20, 40]
SLOT_MINUTE_MARKS = list(range(0, 60, SLOT_INTERVAL_MINUTES))
