from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.application.ports.pms import PmsGateway
from app.infrastructure.database.call_store import (
    CallStore,
    FollowUpResult,
    StartCall,
    StartCallResult,
)


@dataclass(frozen=True, slots=True)
class PatientLookup:
    match_count: int
    mode: str
    patient_id: str | None = None


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    call: StartCallResult
    patient_lookup: PatientLookup


class CallService:
    _EPHEMERAL_CHECKPOINT_KEYS = {
        "availability_token",
        "availability_tokens",
        "availability_query_id",
        "offered_slots",
    }

    def __init__(
        self,
        store: CallStore,
        pms: PmsGateway,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._pms = pms
        self._clock = clock or (lambda: datetime.now(UTC))

    async def bootstrap(self, request: StartCall) -> BootstrapResult:
        started = await self._store.start(request, now=self._clock())
        patients = await self._pms.find_patients_by_phone(started.session.caller_phone_e164)
        if len(patients) == 1:
            lookup = PatientLookup(1, "verify_full_name", patients[0].id)
        elif len(patients) > 1:
            lookup = PatientLookup(len(patients), "disambiguate")
        else:
            lookup = PatientLookup(0, "new_patient")
        return BootstrapResult(started, lookup)

    async def save_checkpoint(
        self,
        session_id: UUID,
        *,
        checkpoint: dict[str, object],
        patient_id: str | None,
        language_mode: str | None,
    ) -> None:
        durable = {
            key: value
            for key, value in checkpoint.items()
            if key not in self._EPHEMERAL_CHECKPOINT_KEYS
        }
        await self._store.save_checkpoint(
            session_id,
            checkpoint=durable,
            patient_id=patient_id,
            language_mode=language_mode,
            now=self._clock(),
        )

    async def log_follow_up(
        self,
        session_id: UUID,
        *,
        idempotency_key: str,
        reason: str,
        details: dict[str, object],
    ) -> FollowUpResult:
        return await self._store.log_follow_up(
            session_id,
            idempotency_key=idempotency_key,
            reason=reason,
            details=details,
            now=self._clock(),
        )
