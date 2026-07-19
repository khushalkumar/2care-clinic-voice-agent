from datetime import datetime

from app.application.ports.pms import CreateAppointment, PmsError, PmsGateway
from app.infrastructure.database.booking_store import BookingStore, PendingBooking


def _request(pending: PendingBooking) -> CreateAppointment:
    payload = pending.request_payload
    try:
        return CreateAppointment(
            business_id=str(payload["business_id"]),
            practitioner_id=str(payload["practitioner_id"]),
            appointment_type_id=str(payload["appointment_type_id"]),
            patient_id=str(payload["patient_id"]),
            starts_at=datetime.fromisoformat(str(payload["starts_at"])),
            ends_at=datetime.fromisoformat(str(payload["ends_at"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid persisted booking payload") from error


class BookingReconciler:
    def __init__(self, pms: PmsGateway, booking_store: BookingStore) -> None:
        self._pms = pms
        self._booking_store = booking_store

    async def run_once(self, *, limit: int = 50) -> int:
        reconciled = 0
        pending_items = await self._booking_store.list_pending_verification(limit=limit)
        for pending in pending_items:
            try:
                appointment = await self._pms.create_appointment(
                    _request(pending), idempotency_key=pending.idempotency_key
                )
            except PmsError:
                continue
            await self._booking_store.mark_confirmed(pending.operation_id, appointment.id)
            reconciled += 1
        return reconciled
