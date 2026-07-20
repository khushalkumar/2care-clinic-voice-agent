import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from urllib.parse import quote_plus

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.app import ApiSettings, create_app
from app.application.ports.pms import PmsGateway
from app.infrastructure.pms.cliniko import ClinikoConfig, ClinikoTransport
from app.infrastructure.pms.cliniko_gateway import ClinikoGateway
from app.infrastructure.pms.mock import MockPmsGateway


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _patient_mapping(values: Mapping[str, str], *, required: bool) -> dict[str, str]:
    raw = values.get("CLINIKO_PATIENT_IDS_BY_PHONE_JSON", "").strip()
    if not raw and not required:
        return {}
    if not raw:
        raise ValueError("CLINIKO_PATIENT_IDS_BY_PHONE_JSON is required for Cliniko")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("CLINIKO_PATIENT_IDS_BY_PHONE_JSON must be valid JSON") from error
    if not isinstance(parsed, dict) or not all(
        isinstance(phone, str)
        and phone.startswith("+")
        and isinstance(patient_id, str)
        and patient_id
        for phone, patient_id in parsed.items()
    ):
        raise ValueError("CLINIKO_PATIENT_IDS_BY_PHONE_JSON must map E.164 phones to patient IDs")
    return parsed


def database_url_from_mapping(values: Mapping[str, str]) -> str:
    database_url = values.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url
    host = _required(values, "DB_HOST")
    port = _required(values, "DB_PORT")
    name = _required(values, "DB_NAME")
    username = quote_plus(_required(values, "DB_USERNAME"))
    password = quote_plus(_required(values, "DB_PASSWORD"))
    return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{name}?ssl=require"


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    app_env: str
    database_url: str
    pms_provider: str
    request_hmac_secret: bytes
    availability_token_secret: bytes
    retell_tool_token: bytes | None = None
    cliniko_api_key: str | None = None
    cliniko_shard: str | None = None
    cliniko_user_agent: str | None = None
    cliniko_patient_ids_by_phone: dict[str, str] | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "RuntimeSettings":
        app_env = values.get("APP_ENV", "local").strip().lower()
        database_url = database_url_from_mapping(values)
        pms_provider = values.get("PMS_PROVIDER", "mock").strip().lower()
        request_secret = _required(values, "REQUEST_HMAC_SECRET")
        availability_secret = _required(values, "AVAILABILITY_TOKEN_SECRET")
        if len(request_secret) < 32 or len(availability_secret) < 32:
            raise ValueError("application secrets must be at least 32 characters")
        retell_tool_token = values.get("RETELL_TOOL_TOKEN", "").strip()
        if retell_tool_token and len(retell_tool_token) < 32:
            raise ValueError("RETELL_TOOL_TOKEN must be at least 32 characters")
        if pms_provider not in {"mock", "cliniko"}:
            raise ValueError("PMS_PROVIDER must be mock or cliniko")
        if app_env == "production" and pms_provider == "mock":
            raise ValueError("production cannot use mock PMS")
        if app_env == "production" and not any(
            marker in database_url for marker in ("ssl=require", "sslmode=require")
        ):
            raise ValueError("production requires an encrypted database connection")

        cliniko_api_key = values.get("CLINIKO_API_KEY") or None
        cliniko_shard = values.get("CLINIKO_SHARD") or None
        cliniko_user_agent = values.get("CLINIKO_USER_AGENT") or None
        if pms_provider == "cliniko" and not all(
            (cliniko_api_key, cliniko_shard, cliniko_user_agent)
        ):
            raise ValueError("Cliniko configuration is incomplete")
        patient_ids_by_phone = _patient_mapping(values, required=pms_provider == "cliniko")
        return cls(
            app_env=app_env,
            database_url=database_url,
            pms_provider=pms_provider,
            request_hmac_secret=request_secret.encode(),
            availability_token_secret=availability_secret.encode(),
            retell_tool_token=retell_tool_token.encode() or None,
            cliniko_api_key=cliniko_api_key,
            cliniko_shard=cliniko_shard,
            cliniko_user_agent=cliniko_user_agent,
            cliniko_patient_ids_by_phone=patient_ids_by_phone,
        )


def build_runtime_app(settings: RuntimeSettings) -> FastAPI:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pms: PmsGateway
    shutdown: Callable[[], Awaitable[None]]
    if settings.pms_provider == "mock":
        pms = MockPmsGateway(sessions)
        shutdown = engine.dispose
    else:
        assert settings.cliniko_api_key is not None
        assert settings.cliniko_shard is not None
        assert settings.cliniko_user_agent is not None
        client = ClinikoTransport(
            ClinikoConfig(
                api_key=settings.cliniko_api_key,
                shard=settings.cliniko_shard,
                user_agent=settings.cliniko_user_agent,
            )
        )
        pms = ClinikoGateway(
            client,
            patient_ids_by_phone=settings.cliniko_patient_ids_by_phone,
        )

        async def shutdown() -> None:
            await client.aclose()
            await engine.dispose()

    app = create_app(
        ApiSettings(
            request_hmac_secret=settings.request_hmac_secret,
            availability_token_secret=settings.availability_token_secret,
            retell_tool_token=settings.retell_tool_token,
        ),
        session_factory=sessions,
        pms=pms,
        shutdown=shutdown,
    )
    return app
