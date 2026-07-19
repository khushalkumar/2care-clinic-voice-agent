import pytest


def _state_api():
    try:
        from app.domain.operation_state import OperationState, transition_operation
    except ImportError:
        pytest.fail("booking operation state machine is not implemented")
    return OperationState, transition_operation


def test_allows_booking_to_progress_from_received_to_confirmed():
    operation_state, transition_operation = _state_api()

    state = transition_operation(operation_state.RECEIVED, operation_state.RESERVED)
    state = transition_operation(state, operation_state.REMOTE_IN_FLIGHT)
    state = transition_operation(state, operation_state.CONFIRMED)

    assert state is operation_state.CONFIRMED


def test_rejects_confirmation_before_remote_write():
    operation_state, transition_operation = _state_api()

    with pytest.raises(ValueError, match="received.*confirmed"):
        transition_operation(operation_state.RECEIVED, operation_state.CONFIRMED)


def test_pending_verification_can_reconcile_to_confirmed():
    operation_state, transition_operation = _state_api()

    state = transition_operation(
        operation_state.REMOTE_IN_FLIGHT,
        operation_state.PENDING_VERIFICATION,
    )

    assert transition_operation(state, operation_state.CONFIRMED) is operation_state.CONFIRMED
