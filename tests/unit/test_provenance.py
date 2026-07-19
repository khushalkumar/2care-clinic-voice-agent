import pytest


def _validator():
    try:
        from app.domain.provenance import validate_source_record
    except ImportError:
        pytest.fail("source provenance validator is not implemented")
    return validate_source_record


def test_accepts_sourced_field_with_official_url_and_retrieval_date():
    validate_source_record = _validator()

    validate_source_record(
        {
            "value": "Physiotattva - Jayanagar Demo",
            "provenance": "sourced",
            "source_url": "https://physiotattva.com/bangalore/jayanagar",
            "retrieved_on": "2026-07-18",
        }
    )


def test_rejects_sourced_field_without_source_url():
    validate_source_record = _validator()

    with pytest.raises(ValueError, match="source_url"):
        validate_source_record(
            {
                "value": "Jayanagar",
                "provenance": "sourced",
                "retrieved_on": "2026-07-18",
            }
        )


def test_rejects_unknown_provenance_label():
    validate_source_record = _validator()

    with pytest.raises(ValueError, match="provenance"):
        validate_source_record({"value": "Jayanagar", "provenance": "probably-real"})
