from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from secrets import compare_digest
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.availability_token import (
    AvailabilityTokenError,
    AvailabilityTokenService,
)
from app.application.booking_service import BookingService, IdentityVerificationError
from app.application.call_service import CallService
from app.application.ports.pms import PmsConflict, PmsError, PmsGateway
from app.application.request_auth import RequestAuthenticator, RequestAuthError, SignedRequest
from app.infrastructure.database.booking_store import BookingStore, SlotAlreadyReserved
from app.infrastructure.database.call_store import CallStore, StartCall
from app.infrastructure.database.replay_store import PostgresReplayStore
from app.observability import log_http_request


@dataclass(frozen=True, slots=True)
class ApiSettings:
    request_hmac_secret: bytes
    availability_token_secret: bytes
    retell_tool_token: bytes | None = None
    max_request_bytes: int = 64 * 1024


class SearchAvailabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    business_id: str
    practitioner_ids: list[str]
    appointment_type_id: str
    starts_at: datetime
    ends_at: datetime


class BookAppointmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    patient_id: str
    full_name: str
    availability_token: str
    idempotency_key: str


class PatientAppointmentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    patient_id: str


class RescheduleAppointmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    appointment_id: str
    starts_at: datetime
    ends_at: datetime
    idempotency_key: str


class CancelAppointmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    appointment_id: str
    idempotency_key: str


class BootstrapCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_call_id: str
    direction: str
    caller_phone: str
    called_phone: str


class SaveCheckpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    checkpoint: dict[str, object]
    patient_id: str | None = None
    language_mode: str | None = None


class LogFollowUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    idempotency_key: str
    reason: str
    details: dict[str, object]


def _error(code: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status_code)


def _appointment_payload(appointment: Any) -> dict[str, Any] | None:
    if appointment is None:
        return None
    return {
        "id": appointment.id,
        "business_id": appointment.business_id,
        "practitioner_id": appointment.practitioner_id,
        "appointment_type_id": appointment.appointment_type_id,
        "patient_id": appointment.patient_id,
        "starts_at": appointment.starts_at.isoformat(),
        "ends_at": appointment.ends_at.isoformat(),
        "status": appointment.status,
    }


def create_app(
    settings: ApiSettings,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    pms: PmsGateway,
    clock: Callable[[], datetime] | None = None,
    shutdown: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    current_time = clock or (lambda: datetime.now(UTC))
    replay_store = PostgresReplayStore(session_factory)
    authenticator = RequestAuthenticator(
        settings.request_hmac_secret, replay_store, clock=current_time
    )
    booking = BookingService(
        pms,
        BookingStore(session_factory),
        AvailabilityTokenService(settings.availability_token_secret, clock=current_time),
        clock=current_time,
    )
    calls = CallService(CallStore(session_factory), pms, clock=current_time)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if shutdown is not None:
                await shutdown()

    app = FastAPI(title="2care Clinic Voice Agent", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def authenticate(request: Request, call_next: Callable[[Request], Any]) -> Any:
        started = perf_counter()
        request_id = (
            request.headers.get("X-2Care-Event-Id")
            or request.headers.get("X-Request-ID")
            or uuid4().hex
        )

        def complete(response: JSONResponse | Any) -> Any:
            response.headers["X-Request-ID"] = request_id
            log_http_request(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=(perf_counter() - started) * 1000,
            )
            return response

        if request.url.path in {"/live", "/ready", "/openapi.json"}:
            return complete(await call_next(request))
        body = await request.body()
        if len(body) > settings.max_request_bytes:
            return complete(_error("request_too_large", 413))
        content_type = request.headers.get("Content-Type", "").split(";", maxsplit=1)[0]
        if request.method in {"POST", "PUT", "PATCH"} and content_type != "application/json":
            return complete(_error("unsupported_media_type", 415))
        platform_token = request.headers.get("X-2Care-Platform-Token", "").encode()
        if (
            request.url.path.startswith("/v1/tools/")
            and settings.retell_tool_token is not None
            and compare_digest(platform_token, settings.retell_tool_token)
        ):
            return complete(await call_next(request))
        timestamp = request.headers.get("X-2Care-Timestamp")
        event_id = request.headers.get("X-2Care-Event-Id")
        signature = request.headers.get("X-2Care-Signature")
        if not timestamp or not event_id or not signature:
            return complete(_error("authentication_required", 401))
        signed = SignedRequest(timestamp, event_id, request.method, request.url.path, body)
        try:
            await authenticator.verify(signed, signature)
        except RequestAuthError as error:
            return complete(_error(str(error), 401))
        return complete(await call_next(request))

    @app.exception_handler(PmsError)
    async def handle_pms_error(request: Request, error: PmsError) -> JSONResponse:
        return _error(error.code, 409 if isinstance(error, PmsConflict) else 502)

    @app.exception_handler(SlotAlreadyReserved)
    async def handle_reservation_conflict(
        request: Request, error: SlotAlreadyReserved
    ) -> JSONResponse:
        return _error("slot_unavailable", 409)

    @app.exception_handler(AvailabilityTokenError)
    async def handle_token_error(request: Request, error: AvailabilityTokenError) -> JSONResponse:
        return _error(str(error), 400)

    @app.exception_handler(IdentityVerificationError)
    async def handle_identity_error(
        request: Request, error: IdentityVerificationError
    ) -> JSONResponse:
        return _error(str(error), 400)

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, error: ValueError) -> JSONResponse:
        return _error("invalid_request", 400)

    @app.exception_handler(LookupError)
    async def handle_lookup_error(request: Request, error: LookupError) -> JSONResponse:
        return _error("not_found", 404)

    @app.get("/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            await pms.list_businesses()
        except Exception:
            return _error("dependency_unavailable", 503)
        return JSONResponse({"status": "ready"})

    @app.get("/v1/tools/clinic-catalog")
    async def clinic_catalog() -> dict[str, list[dict[str, Any]]]:
        businesses = await pms.list_businesses()
        practitioners = [
            practitioner
            for business in businesses
            for practitioner in await pms.list_practitioners(business.id)
        ]
        appointment_types = await pms.list_appointment_types()
        return {
            "businesses": [
                {"id": business.id, "name": business.name, "timezone": business.timezone}
                for business in businesses
            ],
            "practitioners": [
                {
                    "id": practitioner.id,
                    "business_id": practitioner.business_id,
                    "name": practitioner.name,
                }
                for practitioner in practitioners
            ],
            "appointment_types": [
                {
                    "id": appointment_type.id,
                    "name": appointment_type.name,
                    "duration_minutes": appointment_type.duration_minutes,
                }
                for appointment_type in appointment_types
            ],
        }

    @app.post("/v1/tools/search-availability")
    async def search_availability(payload: SearchAvailabilityRequest) -> dict[str, Any]:
        offered = await booking.search_availability(
            call_id=payload.call_id,
            business_id=payload.business_id,
            practitioner_ids=payload.practitioner_ids,
            appointment_type_id=payload.appointment_type_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
        )
        return {
            "slots": [
                {
                    "business_id": item.slot.business_id,
                    "practitioner_id": item.slot.practitioner_id,
                    "appointment_type_id": item.slot.appointment_type_id,
                    "starts_at": item.slot.starts_at.isoformat(),
                    "ends_at": item.slot.ends_at.isoformat(),
                    "availability_token": item.availability_token,
                }
                for item in offered
            ]
        }

    @app.post("/v1/tools/bootstrap-call")
    async def bootstrap_call(payload: BootstrapCallRequest) -> dict[str, Any]:
        result = await calls.bootstrap(
            StartCall(
                payload.platform_call_id,
                payload.direction,
                payload.caller_phone,
                payload.called_phone,
            )
        )
        session = result.call.session
        callback = None
        if session.callback_purpose is not None:
            callback = {
                "campaign": session.callback_campaign,
                "purpose": session.callback_purpose,
            }
        lookup: dict[str, Any] = {
            "match_count": result.patient_lookup.match_count,
            "mode": result.patient_lookup.mode,
        }
        if result.patient_lookup.patient_id is not None:
            lookup["patient_id"] = result.patient_lookup.patient_id
        return {
            "session_id": str(session.id),
            "replayed": result.call.replayed,
            "resumed": session.resumed_from_id is not None,
            "checkpoint": session.checkpoint,
            "patient_lookup": lookup,
            "callback_context": callback,
        }

    @app.post("/v1/tools/save-call-checkpoint")
    async def save_call_checkpoint(payload: SaveCheckpointRequest) -> dict[str, str]:
        await calls.save_checkpoint(
            payload.session_id,
            checkpoint=payload.checkpoint,
            patient_id=payload.patient_id,
            language_mode=payload.language_mode,
        )
        return {"status": "saved"}

    @app.post("/v1/tools/log-follow-up")
    async def log_follow_up(payload: LogFollowUpRequest) -> dict[str, Any]:
        result = await calls.log_follow_up(
            payload.session_id,
            idempotency_key=payload.idempotency_key,
            reason=payload.reason,
            details=payload.details,
        )
        return {"follow_up_id": str(result.follow_up_id), "replayed": result.replayed}

    @app.post("/v1/tools/book-appointment")
    async def book_appointment(payload: BookAppointmentRequest) -> dict[str, Any]:
        outcome = await booking.book(
            call_id=payload.call_id,
            patient_id=payload.patient_id,
            full_name=payload.full_name,
            availability_token=payload.availability_token,
            idempotency_key=payload.idempotency_key,
        )
        return {
            "status": outcome.status,
            "operation_id": outcome.operation_id,
            "appointment": _appointment_payload(outcome.appointment),
        }

    @app.post("/v1/tools/list-patient-appointments")
    async def list_patient_appointments(
        payload: PatientAppointmentsRequest,
    ) -> dict[str, Any]:
        appointments = await booking.list_patient_appointments(payload.patient_id)
        return {"appointments": [_appointment_payload(appointment) for appointment in appointments]}

    @app.post("/v1/tools/reschedule-appointment")
    async def reschedule_appointment(
        payload: RescheduleAppointmentRequest,
    ) -> dict[str, Any]:
        appointment = await booking.reschedule(
            appointment_id=payload.appointment_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            idempotency_key=payload.idempotency_key,
        )
        return {"status": "confirmed", "appointment": _appointment_payload(appointment)}

    @app.post("/v1/tools/cancel-appointment")
    async def cancel_appointment(payload: CancelAppointmentRequest) -> dict[str, Any]:
        appointment = await booking.cancel(
            appointment_id=payload.appointment_id,
            idempotency_key=payload.idempotency_key,
        )
        return {"status": "confirmed", "appointment": _appointment_payload(appointment)}

    return app
