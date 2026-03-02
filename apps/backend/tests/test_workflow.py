from __future__ import annotations

import pytest

from agent1.core.contracts import JobState
from agent1.core.workflow import compute_can_transition
from agent1.core.workflow import require_transition


def test_compute_can_transition_returns_true_for_allowed_pair() -> None:
    assert compute_can_transition(JobState.AWAITING_CONTEXT, JobState.READY_TO_EXECUTE) is True


def test_compute_can_transition_returns_false_for_disallowed_pair() -> None:
    assert compute_can_transition(JobState.AWAITING_CI, JobState.EXECUTING) is False


def test_require_transition_raises_for_disallowed_pair() -> None:
    with pytest.raises(ValueError):
        require_transition(JobState.COMPLETED, JobState.EXECUTING)
