import pytest

from app.runtime import RuntimeSettings, build_runtime_app


def _environment() -> dict[str, str]:
    return {
        "APP_ENV": "local",
        "DATABASE_URL": "postgresql+asyncpg://voice:voice@localhost/voice",
        "PMS_PROVIDER": "mock",
        "REQUEST_HMAC_SECRET": "h" * 32,
        "AVAILABILITY_TOKEN_SECRET": "t" * 32,
    }


def test_local_mock_configuration_is_valid() -> None:
    settings = RuntimeSettings.from_mapping(_environment())

    assert settings.app_env == "local"
    assert settings.pms_provider == "mock"
    assert build_runtime_app(settings).title == "2care Clinic Voice Agent"


def test_production_rejects_mock_pms_and_insecure_database() -> None:
    environment = _environment() | {"APP_ENV": "production"}

    with pytest.raises(ValueError, match="production cannot use mock PMS"):
        RuntimeSettings.from_mapping(environment)

    environment |= {
        "PMS_PROVIDER": "cliniko",
        "CLINIKO_API_KEY": "key",
        "CLINIKO_SHARD": "au4",
        "CLINIKO_USER_AGENT": "2care contact@example.com",
    }
    with pytest.raises(ValueError, match="encrypted database connection"):
        RuntimeSettings.from_mapping(environment)


def test_cliniko_configuration_requires_a_phone_to_patient_mapping() -> None:
    environment = _environment() | {
        "PMS_PROVIDER": "cliniko",
        "CLINIKO_API_KEY": "key",
        "CLINIKO_SHARD": "au5",
        "CLINIKO_USER_AGENT": "2care contact@example.com",
        "CLINIKO_PATIENT_IDS_BY_PHONE_JSON": '{"+919999999999":"patient-1"}',
    }

    settings = RuntimeSettings.from_mapping(environment)

    assert settings.cliniko_patient_ids_by_phone == {"+919999999999": "patient-1"}
    assert build_runtime_app(settings).title == "2care Clinic Voice Agent"


def test_short_or_missing_secrets_fail_at_startup() -> None:
    environment = _environment() | {"REQUEST_HMAC_SECRET": "short"}

    with pytest.raises(ValueError, match="at least 32 characters"):
        RuntimeSettings.from_mapping(environment)


def test_ecs_database_fields_build_an_encrypted_url() -> None:
    environment = _environment()
    environment.pop("DATABASE_URL")
    environment |= {
        "DB_HOST": "database.internal",
        "DB_PORT": "5432",
        "DB_NAME": "voice_agent",
        "DB_USERNAME": "voice_agent_admin",
        "DB_PASSWORD": "p@ss word",
    }

    settings = RuntimeSettings.from_mapping(environment)

    assert settings.database_url == (
        "postgresql+asyncpg://voice_agent_admin:p%40ss+word@"
        "database.internal:5432/voice_agent?ssl=require"
    )
