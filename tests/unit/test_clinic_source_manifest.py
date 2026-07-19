import json
from pathlib import Path

from app.domain.provenance import validate_source_record

MANIFEST_PATH = Path(__file__).parents[2] / "data" / "clinic_source_manifest.json"


def _provenance_records(value):
    if isinstance(value, dict):
        if "provenance" in value:
            yield value
        for child in value.values():
            yield from _provenance_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _provenance_records(child)


def test_every_clinic_fact_has_valid_provenance():
    assert MANIFEST_PATH.exists(), "clinic source manifest is not implemented"
    manifest = json.loads(MANIFEST_PATH.read_text())
    records = list(_provenance_records(manifest))

    assert records, "clinic source manifest contains no provenance records"
    for record in records:
        validate_source_record(record)
