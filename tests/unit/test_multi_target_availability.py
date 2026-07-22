from datetime import UTC, datetime, timedelta

import pytest

from app.application.availability_token import AvailabilityTokenService
from app.application.booking_service import AvailabilitySearchTarget, BookingService
from app.application.ports.pms import AvailableTime


class AvailabilityPms:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search_available_times(
        self,
        *,
        business_id: str,
        practitioner_ids: list[str],
        appointment_type_id: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[AvailableTime]:
        del starts_at, ends_at
        self.calls.append(business_id)
        hour = 5 if business_id == "jayanagar" else 4
        return [
            AvailableTime(
                business_id=business_id,
                practitioner_id=practitioner_ids[0],
                appointment_type_id=appointment_type_id,
                starts_at=datetime(2026, 7, 24, hour, minute, tzinfo=UTC),
                ends_at=datetime(2026, 7, 24, hour, minute, tzinfo=UTC) + timedelta(minutes=30),
            )
            for minute in (0, 30)
        ]


@pytest.mark.asyncio
async def test_multi_target_search_globally_ranks_and_bounds_voice_results() -> None:
    pms = AvailabilityPms()
    now = datetime(2026, 7, 22, 0, 0, tzinfo=UTC)
    service = BookingService(
        pms,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        AvailabilityTokenService(b"t" * 32, clock=lambda: now),
        clock=lambda: now,
    )

    result = await service.search_availability_across_targets(
        session_id="00000000-0000-0000-0000-000000000001",
        targets=[
            AvailabilitySearchTarget("jayanagar", ("nadia-zainab",), "initial"),
            AvailabilitySearchTarget("indiranagar", ("manjiri-arvind",), "initial"),
        ],
        starts_at=datetime(2026, 7, 24, 3, 30, tzinfo=UTC),
        ends_at=datetime(2026, 7, 24, 7, 30, tzinfo=UTC),
    )

    assert pms.calls == ["jayanagar", "indiranagar"]
    assert result.total_slot_count == 4
    assert result.truncated is True
    assert len(result.slots) == 3
    assert [item.slot.business_id for item in result.slots] == [
        "indiranagar",
        "indiranagar",
        "jayanagar",
    ]
    assert [item.slot.starts_at for item in result.slots] == sorted(
        item.slot.starts_at for item in result.slots
    )
    assert all(item.availability_token for item in result.slots)


@pytest.mark.asyncio
@pytest.mark.parametrize("target_count", [0, 5])
async def test_multi_target_search_rejects_unsafe_fan_out(target_count: int) -> None:
    pms = AvailabilityPms()
    now = datetime(2026, 7, 22, 0, 0, tzinfo=UTC)
    service = BookingService(
        pms,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        AvailabilityTokenService(b"t" * 32, clock=lambda: now),
        clock=lambda: now,
    )
    targets = [
        AvailabilitySearchTarget(f"branch-{index}", (f"doctor-{index}",), "initial")
        for index in range(target_count)
    ]

    with pytest.raises(ValueError, match="between 1 and 4"):
        await service.search_availability_across_targets(
            session_id="00000000-0000-0000-0000-000000000001",
            targets=targets,
            starts_at=datetime(2026, 7, 24, 3, 30, tzinfo=UTC),
            ends_at=datetime(2026, 7, 24, 7, 30, tzinfo=UTC),
        )

    assert pms.calls == []


@pytest.mark.asyncio
async def test_multi_target_search_validates_every_target_before_calling_pms() -> None:
    pms = AvailabilityPms()
    now = datetime(2026, 7, 22, 0, 0, tzinfo=UTC)
    service = BookingService(
        pms,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        AvailabilityTokenService(b"t" * 32, clock=lambda: now),
        clock=lambda: now,
    )

    with pytest.raises(ValueError, match="requires practitioners"):
        await service.search_availability_across_targets(
            session_id="00000000-0000-0000-0000-000000000001",
            targets=[
                AvailabilitySearchTarget("jayanagar", ("nadia-zainab",), "initial"),
                AvailabilitySearchTarget("indiranagar", (), "initial"),
            ],
            starts_at=datetime(2026, 7, 24, 3, 30, tzinfo=UTC),
            ends_at=datetime(2026, 7, 24, 7, 30, tzinfo=UTC),
        )

    assert pms.calls == []
