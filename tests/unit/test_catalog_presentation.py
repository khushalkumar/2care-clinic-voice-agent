from app.api.app import split_appointment_type_name


def test_split_appointment_type_name_supports_cliniko_em_dash() -> None:
    assert split_appointment_type_name("Jayanagar — Initial consultation") == (
        "Jayanagar",
        "Initial consultation",
    )


def test_split_appointment_type_name_supports_ascii_separator() -> None:
    assert split_appointment_type_name("Indiranagar - Follow-up") == (
        "Indiranagar",
        "Follow-up",
    )


def test_split_appointment_type_name_preserves_unqualified_name() -> None:
    assert split_appointment_type_name("Initial consultation") == (
        None,
        "Initial consultation",
    )
