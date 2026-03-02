from __future__ import annotations

from agent1.core.contracts import JobState

ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.AWAITING_CONTEXT: {
        JobState.READY_TO_EXECUTE,
        JobState.BLOCKED,
    },
    JobState.READY_TO_EXECUTE: {
        JobState.EXECUTING,
        JobState.COMPLETED,
        JobState.BLOCKED,
    },
    JobState.EXECUTING: {
        JobState.AWAITING_HUMAN_FEEDBACK,
        JobState.AWAITING_CI,
        JobState.BLOCKED,
    },
    JobState.AWAITING_HUMAN_FEEDBACK: {
        JobState.READY_TO_EXECUTE,
        JobState.COMPLETED,
        JobState.BLOCKED,
    },
    JobState.AWAITING_CI: {
        JobState.READY_TO_EXECUTE,
        JobState.COMPLETED,
        JobState.BLOCKED,
    },
    JobState.BLOCKED: {
        JobState.AWAITING_CONTEXT,
        JobState.READY_TO_EXECUTE,
        JobState.COMPLETED,
    },
    JobState.COMPLETED: set(),
}


def get_allowed_transitions(state: JobState) -> set[JobState]:

    '''
    Create allowed next-state set for deterministic workflow transitions.

    Args:
    state (JobState): Current lifecycle state.

    Returns:
    set[JobState]: Allowed next states for the provided state.
    '''

    return ALLOWED_TRANSITIONS[state]


def compute_can_transition(from_state: JobState, to_state: JobState) -> bool:

    '''
    Compute whether a lifecycle transition is allowed by workflow policy.

    Args:
    from_state (JobState): Current lifecycle state.
    to_state (JobState): Requested next lifecycle state.

    Returns:
    bool: True when transition is allowed, otherwise False.
    '''

    return to_state in get_allowed_transitions(from_state)


def require_transition(from_state: JobState, to_state: JobState) -> None:

    '''
    Create transition guard by raising when lifecycle transition is invalid.

    Args:
    from_state (JobState): Current lifecycle state.
    to_state (JobState): Requested next lifecycle state.

    Raises:
    ValueError: Transition is not allowed by workflow policy.
    '''

    if compute_can_transition(from_state, to_state):
        return

    message = f'Invalid transition: {from_state.value} -> {to_state.value}'
    raise ValueError(message)


__all__ = [
    'ALLOWED_TRANSITIONS',
    'compute_can_transition',
    'get_allowed_transitions',
    'require_transition',
]
