from datetime import UTC, datetime

import pytest


def _local_date_function():
    try:
        from app.domain.clock import clinic_local_date
    except ImportError:
        pytest.fail("clinic-local date conversion is not implemented")
    return clinic_local_date


def test_converts_utc_timestamp_to_kolkata_calendar_date():
    clinic_local_date = _local_date_function()
    call_time = datetime(2026, 7, 18, 20, 15, tzinfo=UTC)

    assert clinic_local_date(call_time).isoformat() == "2026-07-19"


def test_rejects_naive_timestamp():
    clinic_local_date = _local_date_function()

    with pytest.raises(ValueError, match="timezone-aware"):
        clinic_local_date(datetime(2026, 7, 18, 20, 15))
