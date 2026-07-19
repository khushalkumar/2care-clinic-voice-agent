from datetime import date, datetime
from zoneinfo import ZoneInfo

CLINIC_TIMEZONE = ZoneInfo("Asia/Kolkata")


def clinic_local_date(timestamp: datetime) -> date:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return timestamp.astimezone(CLINIC_TIMEZONE).date()
