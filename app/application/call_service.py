from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.application.ports.pms import Patient, PmsGateway, PmsValidationError
from app.infrastructure.database.call_store import (
    CallSessionRecord,
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


class CallAuthorizationError(Exception):
    pass


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
        phone = started.session.caller_phone_e164
        mapped_ids = await self._store.patient_ids_for_phone(phone)
        patients = [
            patient
            for patient_id in mapped_ids
            if (patient := await self._pms.get_patient(patient_id)) is not None
            and patient.phone_e164 == phone
        ]
        if not patients:
            patients = list(await self._pms.find_patients_by_phone(phone))
            for patient in patients:
                await self._store.bind_phone_identity(
                    phone, patient.id, source="pms_lookup", now=self._clock()
                )
        if len(patients) == 1:
            patient = patients[0]
            if not await self._store.bind_patient(
                started.session.id, patient.id, now=self._clock()
            ):
                raise CallAuthorizationError("patient_mismatch")
            lookup = PatientLookup(1, "recognized_by_phone", patient.id)
        elif len(patients) > 1:
            lookup = PatientLookup(len(patients), "disambiguate")
        else:
            lookup = PatientLookup(0, "new_patient")
        return BootstrapResult(started, lookup)

    async def authorize_patient(self, session_id: UUID, patient_id: str, full_name: str) -> None:
        session = await self.require_active_session(session_id)
        patient = await self._pms.get_patient(patient_id)
        if patient is None:
            raise CallAuthorizationError("patient_not_found")
        if patient.phone_e164 != session.caller_phone_e164:
            raise CallAuthorizationError("patient_phone_mismatch")
        supplied_name = " ".join(full_name.casefold().split())
        expected_name = " ".join(patient.full_name.casefold().split())
        if not supplied_name or supplied_name != expected_name:
            raise CallAuthorizationError("full_name_mismatch")
        if not await self._store.bind_patient(session_id, patient_id, now=self._clock()):
            raise CallAuthorizationError("patient_mismatch")
        await self._store.bind_phone_identity(
            session.caller_phone_e164,
            patient_id,
            source="authorized_call",
            now=self._clock(),
        )

    async def authorize_phone_patient(self, session_id: UUID, patient_id: str) -> None:
        session = await self.require_active_session(session_id)
        if session.patient_id != patient_id:
            raise CallAuthorizationError("patient_mismatch")
        patient = await self._pms.get_patient(patient_id)
        if patient is None:
            raise CallAuthorizationError("patient_not_found")
        if patient.phone_e164 != session.caller_phone_e164:
            raise CallAuthorizationError("patient_phone_mismatch")

    async def register_new_patient(
        self, session_id: UUID, full_name: str, *, idempotency_key: str
    ) -> Patient:
        session = await self.require_active_session(session_id)
        supplied_name = " ".join(full_name.casefold().split())
        if not supplied_name:
            raise CallAuthorizationError("full_name_required")

        if session.patient_id is not None:
            await self.authorize_patient(session_id, session.patient_id, full_name)
            patient = await self._pms.get_patient(session.patient_id)
            if patient is None:
                raise CallAuthorizationError("patient_not_found")
            return patient

        existing = await self._pms.find_patients_by_phone(session.caller_phone_e164)
        matching = [
            patient
            for patient in existing
            if " ".join(patient.full_name.casefold().split()) == supplied_name
        ]
        if len(matching) == 1:
            patient = matching[0]
        elif existing:
            raise CallAuthorizationError("full_name_mismatch")
        else:
            try:
                patient = await self._pms.create_patient(
                    full_name=full_name.strip(),
                    phone_e164=session.caller_phone_e164,
                    idempotency_key=idempotency_key,
                )
            except PmsValidationError as error:
                raise CallAuthorizationError(error.code) from error

        if patient.phone_e164 != session.caller_phone_e164:
            raise CallAuthorizationError("patient_phone_mismatch")
        if " ".join(patient.full_name.casefold().split()) != supplied_name:
            raise CallAuthorizationError("full_name_mismatch")
        if not await self._store.bind_patient(session_id, patient.id, now=self._clock()):
            raise CallAuthorizationError("patient_mismatch")
        await self._store.bind_phone_identity(
            session.caller_phone_e164,
            patient.id,
            source="patient_registration",
            now=self._clock(),
        )
        return patient

    async def require_active_session(self, session_id: UUID) -> CallSessionRecord:
        session = await self._store.get(session_id)
        if session is None:
            raise CallAuthorizationError("call_session_not_found")
        if session.status != "active":
            raise CallAuthorizationError("call_session_inactive")
        return session

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
