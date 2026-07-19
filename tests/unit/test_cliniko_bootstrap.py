import pytest

from app.infrastructure.pms.cliniko_bootstrap import build_bootstrap_plan, inspect_trial
from scripts.bootstrap_cliniko import parse_args


def test_build_bootstrap_plan_maps_the_existing_two_practitioner_trial_setup() -> None:
    plan = build_bootstrap_plan(
        businesses=[{"id": "business-1", "business_name": "Physiotattva Demo Clinic"}],
        practitioners=[
            {"id": "practitioner-1", "first_name": "Nadia", "last_name": "Zainab"},
            {"id": "practitioner-2", "first_name": "Silki", "last_name": "Gupta"},
        ],
        appointment_types=[
            {"id": "type-1", "name": "Jayanagar - Initial consultation"},
            {"id": "type-2", "name": "Jayanagar - Follow-up"},
            {"id": "type-3", "name": "Indiranagar - Initial consultation"},
            {"id": "type-4", "name": "Indiranagar - Follow-up"},
        ],
    )

    assert plan.mapping == {
        "business": "business-1",
        "practitioners": {"jayanagar": "practitioner-1", "indiranagar": "practitioner-2"},
        "appointment_types": {
            "jayanagar_initial": "type-1",
            "jayanagar_follow_up": "type-2",
            "indiranagar_initial": "type-3",
            "indiranagar_follow_up": "type-4",
        },
    }
    assert plan.missing == ()


def test_build_bootstrap_plan_rejects_ambiguous_or_missing_records() -> None:
    with pytest.raises(ValueError, match="missing appointment type: Indiranagar - Follow-up"):
        build_bootstrap_plan(
            businesses=[{"id": "business-1", "business_name": "Physiotattva Demo Clinic"}],
            practitioners=[
                {"id": "practitioner-1", "first_name": "Nadia", "last_name": "Zainab"},
                {"id": "practitioner-2", "first_name": "Silki", "last_name": "Gupta"},
            ],
            appointment_types=[
                {"id": "type-1", "name": "Jayanagar - Initial consultation"},
                {"id": "type-2", "name": "Jayanagar - Follow-up"},
                {"id": "type-3", "name": "Indiranagar - Initial consultation"},
            ],
        )


async def test_inspect_trial_returns_a_redacted_dry_run_report() -> None:
    class TrialClient:
        async def get_all(self, path: str, *, collection: str) -> list[dict[str, str]]:
            assert path == collection
            return {
                "businesses": [
                    {"id": "business-secret", "business_name": "Physiotattva Demo Clinic"}
                ],
                "practitioners": [
                    {"id": "practitioner-secret-1", "first_name": "Nadia", "last_name": "Zainab"},
                    {"id": "practitioner-secret-2", "first_name": "Silki", "last_name": "Gupta"},
                ],
                "appointment_types": [
                    {"id": "type-secret-1", "name": "Jayanagar - Initial consultation"},
                    {"id": "type-secret-2", "name": "Jayanagar - Follow-up"},
                    {"id": "type-secret-3", "name": "Indiranagar - Initial consultation"},
                    {"id": "type-secret-4", "name": "Indiranagar - Follow-up"},
                ],
            }[collection]

    report = await inspect_trial(TrialClient())  # type: ignore[arg-type]

    assert report == {
        "dry_run": True,
        "business_count": 1,
        "practitioner_count": 2,
        "appointment_type_count": 4,
        "mapped_branches": ["indiranagar", "jayanagar"],
        "mapped_appointment_type_keys": [
            "indiranagar_follow_up",
            "indiranagar_initial",
            "jayanagar_follow_up",
            "jayanagar_initial",
        ],
        "online_bookings_prerequisite": "verify in Cliniko before availability checks",
    }


def test_bootstrap_command_accepts_an_explicit_dry_run_flag() -> None:
    assert parse_args(["--dry-run"]).apply is False
