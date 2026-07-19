from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class BootstrapPlan:
    mapping: dict[str, object]
    missing: tuple[str, ...]


class TrialReader(Protocol):
    async def get_all(self, path: str, *, collection: str) -> list[dict[str, Any]]: ...


async def inspect_trial(client: TrialReader) -> dict[str, object]:
    businesses = await client.get_all("businesses", collection="businesses")
    practitioners = await client.get_all("practitioners", collection="practitioners")
    appointment_types = await client.get_all("appointment_types", collection="appointment_types")
    plan = build_bootstrap_plan(
        businesses=businesses,
        practitioners=practitioners,
        appointment_types=appointment_types,
    )
    branch_mapping = plan.mapping["practitioners"]
    type_mapping = plan.mapping["appointment_types"]
    assert isinstance(branch_mapping, dict)
    assert isinstance(type_mapping, dict)
    return {
        "dry_run": True,
        "business_count": len(businesses),
        "practitioner_count": len(practitioners),
        "appointment_type_count": len(appointment_types),
        "mapped_branches": sorted(branch_mapping),
        "mapped_appointment_type_keys": sorted(type_mapping),
        "online_bookings_prerequisite": "verify in Cliniko before availability checks",
    }


def build_bootstrap_plan(
    *,
    businesses: list[dict[str, Any]],
    practitioners: list[dict[str, Any]],
    appointment_types: list[dict[str, Any]],
) -> BootstrapPlan:
    business = _find_one(businesses, "business_name", "Physiotattva Demo Clinic", "business")
    branch_practitioners = {
        "jayanagar": _find_person(practitioners, "Nadia", "Zainab"),
        "indiranagar": _find_person(practitioners, "Silki", "Gupta"),
    }
    type_names = {
        "jayanagar_initial": "Jayanagar - Initial consultation",
        "jayanagar_follow_up": "Jayanagar - Follow-up",
        "indiranagar_initial": "Indiranagar - Initial consultation",
        "indiranagar_follow_up": "Indiranagar - Follow-up",
    }
    return BootstrapPlan(
        mapping={
            "business": _id_of(business, "business"),
            "practitioners": {
                branch: _id_of(practitioner, f"{branch} practitioner")
                for branch, practitioner in branch_practitioners.items()
            },
            "appointment_types": {
                key: _id_of(_find_one(appointment_types, "name", name, "appointment type"), name)
                for key, name in type_names.items()
            },
        },
        missing=(),
    )


def _find_person(records: list[dict[str, Any]], first_name: str, last_name: str) -> dict[str, Any]:
    matches = [
        record
        for record in records
        if _normalise(record.get("first_name")) == _normalise(first_name)
        and _normalise(record.get("last_name")) == _normalise(last_name)
    ]
    return _exactly_one(matches, f"practitioner: {first_name} {last_name}")


def _find_one(
    records: list[dict[str, Any]], field: str, expected: str, label: str
) -> dict[str, Any]:
    matches = [
        record for record in records if _normalise(record.get(field)) == _normalise(expected)
    ]
    return _exactly_one(matches, f"{label}: {expected}")


def _exactly_one(matches: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if not matches:
        raise ValueError(f"missing {label}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous {label}")
    return matches[0]


def _id_of(record: dict[str, Any], label: str) -> str:
    value = record.get("id")
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing id for {label}")
    return value


def _normalise(value: object) -> str:
    return str(value).replace("—", "-").casefold().strip()
