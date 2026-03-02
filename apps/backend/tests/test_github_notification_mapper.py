from __future__ import annotations

from agent1.adapters.github.notification_mapper import GitHubNotificationMapper
from agent1.core.ingress_contracts import IngressEventType


def test_mapper_maps_issue_mention_notification() -> None:
    mapper = GitHubNotificationMapper()
    payload = {
        'id': 'evt_10',
        'reason': 'mention',
        'updated_at': '2026-03-02T12:00:00Z',
        'subject': {
            'type': 'Issue',
            'url': 'https://api.github.com/repos/Vaquum/Agent1/issues/10',
        },
        'repository': {
            'full_name': 'Vaquum/Agent1',
            'owner': {'login': 'mikkokotila'},
        },
    }

    mapped = mapper.map_notification(payload)

    assert mapped is not None
    assert mapped.event_id == 'evt_10'
    assert mapped.event_type == IngressEventType.ISSUE_MENTION


def test_mapper_maps_review_requested_notification() -> None:
    mapper = GitHubNotificationMapper()
    payload = {
        'id': 'evt_11',
        'reason': 'review_requested',
        'updated_at': '2026-03-02T12:00:00Z',
        'subject': {
            'type': 'PullRequest',
            'url': 'https://api.github.com/repos/Vaquum/Agent1/pulls/11',
        },
        'repository': {
            'full_name': 'Vaquum/Agent1',
            'owner': {'login': 'mikkokotila'},
        },
    }

    mapped = mapper.map_notification(payload)

    assert mapped is not None
    assert mapped.event_type == IngressEventType.PR_REVIEW_REQUESTED


def test_mapper_returns_none_for_non_actionable_reason() -> None:
    mapper = GitHubNotificationMapper()
    payload = {
        'id': 'evt_12',
        'reason': 'subscribed',
        'updated_at': '2026-03-02T12:00:00Z',
        'subject': {
            'type': 'Issue',
            'url': 'https://api.github.com/repos/Vaquum/Agent1/issues/12',
        },
        'repository': {
            'full_name': 'Vaquum/Agent1',
            'owner': {'login': 'mikkokotila'},
        },
    }

    mapped = mapper.map_notification(payload)

    assert mapped is None


def test_mapper_maps_issue_comment_to_issue_updated() -> None:
    mapper = GitHubNotificationMapper()
    payload = {
        'id': 'evt_13',
        'reason': 'comment',
        'updated_at': '2026-03-02T12:00:00Z',
        'subject': {
            'type': 'Issue',
            'url': 'https://api.github.com/repos/Vaquum/Agent1/issues/13',
        },
        'repository': {
            'full_name': 'Vaquum/Agent1',
            'owner': {'login': 'mikkokotila'},
        },
    }

    mapped = mapper.map_notification(payload)

    assert mapped is not None
    assert mapped.event_type == IngressEventType.ISSUE_UPDATED
    assert mapped.details['has_sufficient_context'] is True
