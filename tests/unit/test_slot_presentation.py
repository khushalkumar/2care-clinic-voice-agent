from datetime import UTC, datetime

from app.application.slot_presentation import spoken_slot_label


def test_spoken_slot_label_uses_india_time_and_words() -> None:
    assert (
        spoken_slot_label(
            datetime(2026, 7, 20, 9, 30, tzinfo=UTC),
            datetime(2026, 7, 20, 10, 0, tzinfo=UTC),
        )
        == "Monday, July 20, 2026 from three PM to three thirty PM"
    )
