from datetime import UTC, datetime, timedelta

import app.application.booking_service as booking_service


def test_same_day_search_is_shifted_past_the_booking_buffer() -> None:
    now = datetime(2026, 7, 20, 4, 0, tzinfo=UTC)
    requested = datetime(2026, 7, 20, 4, 15, tzinfo=UTC)

    assert hasattr(booking_service, "apply_same_day_buffer")
    effective = booking_service.apply_same_day_buffer(
        requested,
        now=now,
        buffer=timedelta(minutes=60),
    )

    assert effective == now + timedelta(minutes=60)


def test_future_day_search_is_not_shifted() -> None:
    now = datetime(2026, 7, 20, 4, 0, tzinfo=UTC)
    requested = datetime(2026, 7, 21, 4, 15, tzinfo=UTC)

    assert (
        booking_service.apply_same_day_buffer(requested, now=now, buffer=timedelta(hours=1))
        == requested
    )
