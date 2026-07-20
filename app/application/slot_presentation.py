from datetime import datetime
from zoneinfo import ZoneInfo

_INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")
_NUMBER_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS_WORDS = ("", "", "twenty", "thirty", "forty", "fifty")


def spoken_slot_label(starts_at: datetime, ends_at: datetime) -> str:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise ValueError("slot times must be timezone-aware")
    if ends_at <= starts_at:
        raise ValueError("slot end must be after slot start")

    local_start = starts_at.astimezone(_INDIA_TIMEZONE)
    local_end = ends_at.astimezone(_INDIA_TIMEZONE)
    start_date = _spoken_date(local_start)
    if local_start.date() == local_end.date():
        return f"{start_date} from {_spoken_time(local_start)} to {_spoken_time(local_end)}"
    return (
        f"{start_date} at {_spoken_time(local_start)} to "
        f"{_spoken_date(local_end)} at {_spoken_time(local_end)}"
    )


def spoken_slot_date(starts_at: datetime) -> str:
    """Return the local date once for a grouped slot list."""
    if starts_at.tzinfo is None:
        raise ValueError("slot time must be timezone-aware")
    return _spoken_date(starts_at.astimezone(_INDIA_TIMEZONE))


def spoken_slot_time_range(starts_at: datetime, ends_at: datetime) -> str:
    """Return a compact local time range for slots sharing one date."""
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise ValueError("slot times must be timezone-aware")
    local_start = starts_at.astimezone(_INDIA_TIMEZONE)
    local_end = ends_at.astimezone(_INDIA_TIMEZONE)
    if local_start.date() != local_end.date():
        return spoken_slot_label(starts_at, ends_at)
    return f"{_spoken_time(local_start)} to {_spoken_time(local_end)}"


def _spoken_date(value: datetime) -> str:
    return f"{value.strftime('%A, %B')} {value.day}, {value.year}"


def _spoken_time(value: datetime) -> str:
    hour = value.hour % 12 or 12
    hour_word = _NUMBER_WORDS[hour]
    meridiem = "AM" if value.hour < 12 else "PM"
    if value.minute == 0:
        return f"{hour_word} {meridiem}"
    minute_word = _number_word(value.minute)
    if value.minute < 10:
        minute_word = f"oh {minute_word}"
    return f"{hour_word} {minute_word} {meridiem}"


def _number_word(value: int) -> str:
    if value < 20:
        return _NUMBER_WORDS[value]
    tens, remainder = divmod(value, 10)
    if remainder == 0:
        return _TENS_WORDS[tens]
    return f"{_TENS_WORDS[tens]}-{_NUMBER_WORDS[remainder]}"
