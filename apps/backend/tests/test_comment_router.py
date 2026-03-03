from __future__ import annotations

import pytest

from agent1.core.contracts import CommentTargetType
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.ingress_contracts import NormalizedIngressEvent
from agent1.core.services.comment_router import CommentRouter
from agent1.core.services.comment_router import CommentRoutingError


def _create_event(details: dict[str, object]) -> NormalizedIngressEvent:
    return NormalizedIngressEvent(
        event_id='evt_router_1',
        trace_id='trc_router_1',
        environment=EnvironmentName.DEV,
        repository='Vaquum/Agent1',
        entity_number=22,
        entity_key='Vaquum/Agent1#22',
        job_id='Vaquum_Agent1#22:pr_author',
        job_kind=JobKind.PR_AUTHOR,
        initial_state=JobState.READY_TO_EXECUTE,
        should_claim_lease=True,
        transition_to=JobState.READY_TO_EXECUTE,
        transition_reason='pr_review_comment',
        idempotency_key='evt_router_1:pr_review_comment',
        details=details,
    )


def test_comment_router_routes_review_thread_target() -> None:
    router = CommentRouter(
        require_review_thread_reply=True,
        allow_top_level_pr_fallback=False,
    )
    event = _create_event(
        {
            'ingress_event_type': 'pr_review_comment',
            'is_review_thread_comment': True,
            'review_comment_id': 1200,
            'thread_id': 'PRRC_kwDOABCD',
            'path': 'apps/backend/src/agent1/main.py',
            'line': 42,
            'side': 'RIGHT',
        }
    )

    target = router.route(event)

    assert target.target_type == CommentTargetType.PR_REVIEW_THREAD
    assert target.review_comment_id == 1200
    assert target.path == 'apps/backend/src/agent1/main.py'


def test_comment_router_raises_without_thread_metadata_under_strict_policy() -> None:
    router = CommentRouter(
        require_review_thread_reply=True,
        allow_top_level_pr_fallback=False,
    )
    event = _create_event(
        {
            'ingress_event_type': 'pr_review_comment',
            'is_review_thread_comment': True,
            'review_comment_id': 1200,
        }
    )

    with pytest.raises(CommentRoutingError):
        router.route(event)
