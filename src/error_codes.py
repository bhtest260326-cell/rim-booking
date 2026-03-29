"""Structured error codes for the rim repair booking system.

Usage:
    from error_codes import ErrorCode
    logger.error(f"[{ErrorCode.EXTRACTION_FAILED}] Claude extraction returned no tool use")
"""


class ErrorCode:
    EXTRACTION_FAILED = "E001"
    CALENDAR_SYNC_FAILED = "E002"
    SMS_SEND_FAILED = "E003"
    MAPS_LOOKUP_FAILED = "E004"
    BOOKING_NOT_FOUND = "E005"
    INVALID_STATE_TRANSITION = "E006"
    CIRCUIT_OPEN = "E007"
    EMAIL_SEND_FAILED = "E008"
    IMAGE_ANALYSIS_FAILED = "E009"
    WEBHOOK_ERROR = "E010"
