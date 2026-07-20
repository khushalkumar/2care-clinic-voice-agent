from datetime import UTC, datetime

from app.application.slot_presentation import (
    spoken_slot_date,
    spoken_slot_label,
    spoken_slot_time_range,
)


def test_spoken_slot_label_uses_india_time_and_words() -> None:
    assert (
        spoken_slot_label(
            datetime(2026, 7, 20, 9, 30, tzinfo=UTC),
            datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        )
        == "Monday, July 20 from three PM to three thirty PM"
    )


def test_grouped_slot_fields_avoid_repeating_date() -> None:
    starts_at = datetime(2026, 7, 21, 3, 30, tzinfo=UTC)
    ends_at = datetime(2026, 7, 21, 4, 0, tzinfo=UTC)

    assert spoken_slot_date(starts_at) == "Tuesday, July 21"
    assert spoken_slot_time_range(starts_at, ends_at) == "nine AM to nine thirty AM"
