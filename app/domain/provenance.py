from collections.abc import Mapping
from typing import Any

PROVENANCE_LABELS = frozenset({"sourced", "derived", "synthetic"})


def validate_source_record(record: Mapping[str, Any]) -> None:
    provenance = record.get("provenance")
    if provenance not in PROVENANCE_LABELS:
        raise ValueError(f"invalid provenance: {provenance!r}")

    if provenance == "sourced":
        if not record.get("source_url"):
            raise ValueError("sourced records require source_url")
        if not record.get("retrieved_on"):
            raise ValueError("sourced records require retrieved_on")
