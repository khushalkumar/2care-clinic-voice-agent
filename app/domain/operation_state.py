from enum import StrEnum


class OperationState(StrEnum):
    RECEIVED = "received"
    RESERVED = "reserved"
    REMOTE_IN_FLIGHT = "remote_in_flight"
    CONFIRMED = "confirmed"
    LOCAL_CONFLICT = "local_conflict"
    REMOTE_CONFLICT = "remote_conflict"
    PENDING_VERIFICATION = "pending_verification"
    COMPENSATING = "compensating"
    CANCELLED = "cancelled"
    FAILED_PERMANENT = "failed_permanent"


_ALLOWED_TRANSITIONS = {
    OperationState.RECEIVED: {
        OperationState.RESERVED,
        OperationState.LOCAL_CONFLICT,
        OperationState.FAILED_PERMANENT,
    },
    OperationState.RESERVED: {
        OperationState.REMOTE_IN_FLIGHT,
        OperationState.REMOTE_CONFLICT,
        OperationState.CANCELLED,
    },
    OperationState.REMOTE_IN_FLIGHT: {
        OperationState.CONFIRMED,
        OperationState.REMOTE_CONFLICT,
        OperationState.PENDING_VERIFICATION,
        OperationState.COMPENSATING,
    },
    OperationState.PENDING_VERIFICATION: {
        OperationState.CONFIRMED,
        OperationState.COMPENSATING,
        OperationState.FAILED_PERMANENT,
    },
    OperationState.COMPENSATING: {
        OperationState.CANCELLED,
        OperationState.FAILED_PERMANENT,
    },
}


def transition_operation(current: OperationState, target: OperationState) -> OperationState:
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid operation transition: {current.value} -> {target.value}")
    return target
