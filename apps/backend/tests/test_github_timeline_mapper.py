from __future__ import annotations

from agent1.adapters.github.timeline_mapper import GitHubTimelineMapper
from agent1.core.ingress_contracts import IngressEventType


def test_timeline_mapper_maps_review_and_comment_events() -> None:
    mapper = GitHubTimelineMapper()
    payloads = [
        {
            'id': 1001,
            'event': 'review_requested',
            'created_at': '2026-03-03T10:00:00Z',
            'actor': {'login': 'mikkokotila'},
        },
        {
            'id': 1002,
            'event': 'commented',
            'created_at': '2026-03-03T10:01:00Z',
            'actor': {'login': 'runtime-agent-user'},
            'node_id': 'PRRC_kwDOABCD',
            'pull_request_review_id': 55,
            'path': 'apps/backend/src/agent1/main.py',
            'line': 41,
            'side': 'RIGHT',
        },
    ]

    mapped_events = mapper.map_timeline_events(
        repository='Vaquum/Agent1',
        pull_number=90,
        timeline_payloads=payloads,
        event_seed='evt_seed',
    )

    assert len(mapped_events) == 2
    assert mapped_events[0].event_type == IngressEventType.PR_REVIEW_REQUESTED
    assert mapped_events[1].event_type == IngressEventType.PR_REVIEW_COMMENT
    assert mapped_events[1].details['is_review_thread_comment'] is True
    assert mapped_events[1].details['review_comment_id'] == 1002
    assert mapped_events[1].details['path'] == 'apps/backend/src/agent1/main.py'


def test_timeline_mapper_marks_commits_as_reviewer_follow_up_candidates() -> None:
    mapper = GitHubTimelineMapper()
    payloads = [
        {
            'id': 1201,
            'event': 'committed',
            'created_at': '2026-03-03T11:00:00Z',
            'actor': {'login': 'mikkokotila'},
        }
    ]

    mapped_events = mapper.map_timeline_events(
        repository='Vaquum/Agent1',
        pull_number=91,
        timeline_payloads=payloads,
        event_seed='evt_seed_reviewer',
        job_kind_hint='pr_reviewer',
    )

    assert len(mapped_events) == 1
    assert mapped_events[0].event_type == IngressEventType.PR_UPDATED
    assert mapped_events[0].details['requires_follow_up'] is True
    assert mapped_events[0].details['job_kind_hint'] == 'pr_reviewer'
