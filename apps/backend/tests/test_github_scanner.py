from __future__ import annotations

from datetime import datetime
from datetime import timezone

from agent1.adapters.github.scanner import InMemoryGitHubIngressScanner
from agent1.adapters.github.scanner import GitHubNotificationScanner
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType


def test_inmemory_github_scanner_returns_event_snapshot() -> None:
    events = [
        GitHubIngressEvent(
            event_id='evt_1',
            repository='Vaquum/Agent1',
            entity_number=1,
            entity_type=IngressEntityType.ISSUE,
            actor='mikkokotila',
            event_type=IngressEventType.ISSUE_MENTION,
            timestamp=datetime.now(timezone.utc),
            details={},
        )
    ]
    scanner = InMemoryGitHubIngressScanner(events)

    scanned_events = scanner.scan()

    assert len(scanned_events) == 1
    assert scanned_events[0].event_id == 'evt_1'


class _FakeGitHubClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def fetch_notifications(
        self,
        since: datetime | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                'since': since,
                'page': page,
                'per_page': per_page,
            }
        )

        if page > 1:
            return []

        return [
            {
                'id': 'evt_2',
                'reason': 'mention',
                'updated_at': '2026-03-02T12:00:00Z',
                'subject': {
                    'type': 'Issue',
                    'url': 'https://api.github.com/repos/Vaquum/Agent1/issues/77',
                },
                'repository': {
                    'full_name': 'Vaquum/Agent1',
                    'owner': {'login': 'mikkokotila'},
                },
            }
        ]

    def fetch_pull_request_timeline(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return []

    def fetch_pull_request_check_runs(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return []

    def fetch_issue(
        self,
        repository: str,
        issue_number: int,
    ) -> dict[str, object]:
        return {
            'labels': [
                {'name': 'agent1-sandbox'},
            ]
        }

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:
        return {
            'labels': [
                {'name': 'agent1-sandbox'},
            ],
            'head': {'ref': 'sandbox/test'},
        }

    def post_issue_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:
        return {'repository': repository, 'issue_number': issue_number, 'body': body}

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        return {
            'repository': repository,
            'pull_number': pull_number,
            'review_comment_id': review_comment_id,
            'body': body,
        }


def test_notification_scanner_maps_payloads_to_ingress_events() -> None:
    github_client = _FakeGitHubClient()
    scanner = GitHubNotificationScanner(github_client=github_client)

    scanned_events = scanner.scan()

    assert len(scanned_events) == 1
    assert scanned_events[0].entity_number == 77
    assert scanned_events[0].event_type == IngressEventType.ISSUE_MENTION
    assert scanned_events[0].details['label_names'] == ['agent1-sandbox']
    assert scanner.get_since_cursor() is not None
    assert len(github_client.calls) == 1


class _FakeEnrichmentClient:
    def __init__(self) -> None:
        self.notification_calls: list[dict[str, object]] = []

    def fetch_notifications(
        self,
        since: datetime | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, object]]:
        self.notification_calls.append({'since': since, 'page': page, 'per_page': per_page})

        if page > 1:
            return []

        return [
            {
                'id': 'evt_pr_1',
                'reason': 'mention',
                'updated_at': '2026-03-03T12:00:00Z',
                'subject': {
                    'type': 'PullRequest',
                    'url': 'https://api.github.com/repos/Vaquum/Agent1/pulls/88',
                },
                'repository': {
                    'full_name': 'Vaquum/Agent1',
                    'owner': {'login': 'mikkokotila'},
                },
            }
        ]

    def fetch_pull_request_timeline(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return [
            {
                'id': 301,
                'event': 'review_requested',
                'created_at': '2026-03-03T12:01:00Z',
                'actor': {'login': 'mikkokotila'},
            }
        ]

    def fetch_pull_request_check_runs(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return [
            {
                'id': 401,
                'name': 'integration-tests',
                'status': 'completed',
                'conclusion': 'failure',
                'completed_at': '2026-03-03T12:02:00Z',
                'app': {'slug': 'github-actions'},
            }
        ]

    def fetch_issue(
        self,
        repository: str,
        issue_number: int,
    ) -> dict[str, object]:
        return {'labels': []}

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:
        return {
            'labels': [
                {'name': 'agent1-sandbox'},
            ],
            'head': {'ref': 'sandbox/reviewer-scope'},
        }

    def post_issue_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:
        return {'repository': repository, 'issue_number': issue_number, 'body': body}

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        return {
            'repository': repository,
            'pull_number': pull_number,
            'review_comment_id': review_comment_id,
            'body': body,
        }


class _FakeCursorStore:
    def __init__(self, initial_cursor: datetime | None = None) -> None:
        self._cursor = initial_cursor
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, datetime]] = []

    def get_cursor(self, source_key: str) -> datetime | None:
        self.get_calls.append(source_key)
        return self._cursor

    def set_cursor(self, source_key: str, cursor_timestamp: datetime) -> None:
        self._cursor = cursor_timestamp
        self.set_calls.append((source_key, cursor_timestamp))


class _FakeReviewerFollowUpClient:
    def fetch_notifications(
        self,
        since: datetime | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, object]]:
        if page > 1:
            return []

        return [
            {
                'id': 'evt_pr_review_req',
                'reason': 'review_requested',
                'updated_at': '2026-03-03T14:00:00Z',
                'subject': {
                    'type': 'PullRequest',
                    'url': 'https://api.github.com/repos/Vaquum/Agent1/pulls/95',
                },
                'repository': {
                    'full_name': 'Vaquum/Agent1',
                    'owner': {'login': 'mikkokotila'},
                },
            }
        ]

    def fetch_pull_request_timeline(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return [
            {
                'id': 503,
                'event': 'committed',
                'created_at': '2026-03-03T14:01:00Z',
                'actor': {'login': 'mikkokotila'},
            }
        ]

    def fetch_pull_request_check_runs(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return []

    def fetch_issue(
        self,
        repository: str,
        issue_number: int,
    ) -> dict[str, object]:
        return {'labels': []}

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:
        return {
            'labels': [
                {'name': 'agent1-sandbox'},
            ],
            'head': {'ref': 'sandbox/reviewer-follow-up'},
        }

    def post_issue_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:
        return {'repository': repository, 'issue_number': issue_number, 'body': body}

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        return {
            'repository': repository,
            'pull_number': pull_number,
            'review_comment_id': review_comment_id,
            'body': body,
        }


def test_notification_scanner_adds_timeline_and_checkrun_enrichment() -> None:
    scanner = GitHubNotificationScanner(
        github_client=_FakeEnrichmentClient(),
        per_page=1,
    )

    scanned_events = scanner.scan()

    event_types = {event.event_type for event in scanned_events}
    assert IngressEventType.PR_MENTION in event_types
    assert IngressEventType.PR_REVIEW_REQUESTED in event_types
    assert IngressEventType.PR_CI_FAILED in event_types
    mention_events = [event for event in scanned_events if event.event_type == IngressEventType.PR_MENTION]
    assert len(mention_events) == 1
    assert mention_events[0].details['label_names'] == ['agent1-sandbox']
    assert mention_events[0].details['head_ref'] == 'sandbox/reviewer-scope'


def test_notification_scanner_marks_reviewer_follow_up_enrichment() -> None:
    scanner = GitHubNotificationScanner(
        github_client=_FakeReviewerFollowUpClient(),
        per_page=1,
    )

    scanned_events = scanner.scan()
    follow_up_events = [
        event
        for event in scanned_events
        if event.event_type == IngressEventType.PR_UPDATED
        and bool(event.details.get('requires_follow_up', False))
    ]

    assert len(follow_up_events) == 1
    assert follow_up_events[0].details['job_kind_hint'] == 'pr_reviewer'


def test_notification_scanner_uses_incremental_since_cursor() -> None:
    github_client = _FakeEnrichmentClient()
    scanner = GitHubNotificationScanner(
        github_client=github_client,
        per_page=100,
    )

    scanner.scan()
    first_since = scanner.get_since_cursor()
    scanner.scan()

    assert first_since is not None
    assert github_client.notification_calls[0]['since'] is None
    assert github_client.notification_calls[1]['since'] == first_since


def test_notification_scanner_loads_and_persists_cursor_store() -> None:
    initial_cursor = datetime(2026, 3, 2, 9, 0, 0, tzinfo=timezone.utc)
    github_client = _FakeEnrichmentClient()
    cursor_store = _FakeCursorStore(initial_cursor=initial_cursor)
    scanner = GitHubNotificationScanner(
        github_client=github_client,
        cursor_store=cursor_store,
        cursor_key='github_notifications',
    )

    scanner.scan()

    assert cursor_store.get_calls == ['github_notifications']
    assert github_client.notification_calls[0]['since'] == initial_cursor
    assert len(cursor_store.set_calls) == 1
    assert cursor_store.set_calls[0][0] == 'github_notifications'
