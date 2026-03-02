from __future__ import annotations

from datetime import datetime
from typing import Protocol

from agent1.adapters.github.check_run_mapper import GitHubCheckRunMapper
from agent1.adapters.github.client import GitHubApiClient
from agent1.adapters.github.client import UrlLibGitHubApiClient
from agent1.adapters.github.notification_mapper import GitHubNotificationMapper
from agent1.adapters.github.timeline_mapper import GitHubTimelineMapper
from agent1.core.contracts import JobKind
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.services.ingress_cursor_store import IngressCursorStore


def _extract_scope_metadata(payload: dict[str, object]) -> dict[str, object]:
    labels_value = payload.get('labels')
    label_names: list[str] = []
    if isinstance(labels_value, list):
        for label in labels_value:
            if not isinstance(label, dict):
                continue
            name_value = label.get('name')
            if isinstance(name_value, str) and name_value != '':
                label_names.append(name_value)

    metadata: dict[str, object] = {'label_names': label_names}
    head_value = payload.get('head')
    if isinstance(head_value, dict):
        ref_value = head_value.get('ref')
        if isinstance(ref_value, str) and ref_value != '':
            metadata['head_ref'] = ref_value

    return metadata


class GitHubIngressScanner(Protocol):
    def scan(self) -> list[GitHubIngressEvent]:
        ...


class GitHubNotificationScanner:
    def __init__(
        self,
        github_client: GitHubApiClient | None = None,
        notification_mapper: GitHubNotificationMapper | None = None,
        timeline_mapper: GitHubTimelineMapper | None = None,
        check_run_mapper: GitHubCheckRunMapper | None = None,
        cursor_store: IngressCursorStore | None = None,
        cursor_key: str = 'github_notifications',
        per_page: int = 100,
        include_enrichment: bool = True,
        initial_since: datetime | None = None,
    ) -> None:
        self._github_client = github_client or UrlLibGitHubApiClient()
        self._notification_mapper = notification_mapper or GitHubNotificationMapper()
        self._timeline_mapper = timeline_mapper or GitHubTimelineMapper()
        self._check_run_mapper = check_run_mapper or GitHubCheckRunMapper()
        self._cursor_store = cursor_store
        self._cursor_key = cursor_key
        self._per_page = per_page
        self._include_enrichment = include_enrichment
        self._since = initial_since
        self._cursor_loaded = initial_since is not None

    def _load_cursor(self) -> None:
        if self._cursor_loaded:
            return

        if self._cursor_store is not None:
            self._since = self._cursor_store.get_cursor(self._cursor_key)
        self._cursor_loaded = True

    def _scan_notification_pages(self) -> list[dict[str, object]]:
        payloads: list[dict[str, object]] = []
        page = 1

        while True:
            page_payloads = self._github_client.fetch_notifications(
                since=self._since,
                page=page,
                per_page=self._per_page,
            )
            if len(page_payloads) == 0:
                break

            payloads.extend(page_payloads)
            if len(page_payloads) < self._per_page:
                break

            page += 1

        return payloads

    def _scan_enrichment_events(
        self,
        notification_events: list[GitHubIngressEvent],
    ) -> list[GitHubIngressEvent]:
        enrichment_events: list[GitHubIngressEvent] = []
        for notification_event in notification_events:
            if notification_event.entity_type != IngressEntityType.PR:
                continue

            timeline_payloads = self._github_client.fetch_pull_request_timeline(
                repository=notification_event.repository,
                pull_number=notification_event.entity_number,
            )
            check_run_payloads = self._github_client.fetch_pull_request_check_runs(
                repository=notification_event.repository,
                pull_number=notification_event.entity_number,
            )

            mapped_timeline_events = self._timeline_mapper.map_timeline_events(
                repository=notification_event.repository,
                pull_number=notification_event.entity_number,
                timeline_payloads=timeline_payloads,
                event_seed=notification_event.event_id,
                job_kind_hint=(
                    JobKind.PR_REVIEWER.value
                    if notification_event.event_type == IngressEventType.PR_REVIEW_REQUESTED
                    else None
                ),
            )
            mapped_check_events = self._check_run_mapper.map_check_runs(
                repository=notification_event.repository,
                pull_number=notification_event.entity_number,
                check_run_payloads=check_run_payloads,
                event_seed=notification_event.event_id,
            )
            for enrichment_event in [*mapped_timeline_events, *mapped_check_events]:
                enrichment_event.details.update(
                    {
                        'label_names': notification_event.details.get('label_names', []),
                        'head_ref': notification_event.details.get('head_ref', ''),
                    }
                )

            enrichment_events.extend(mapped_timeline_events)
            enrichment_events.extend(mapped_check_events)

        return enrichment_events

    def _annotate_scope_metadata(self, notification_events: list[GitHubIngressEvent]) -> None:
        for notification_event in notification_events:
            if notification_event.entity_type == IngressEntityType.PR:
                pull_payload = self._github_client.fetch_pull_request(
                    repository=notification_event.repository,
                    pull_number=notification_event.entity_number,
                )
                notification_event.details.update(_extract_scope_metadata(pull_payload))
                continue

            issue_payload = self._github_client.fetch_issue(
                repository=notification_event.repository,
                issue_number=notification_event.entity_number,
            )
            notification_event.details.update(_extract_scope_metadata(issue_payload))

    def scan(self) -> list[GitHubIngressEvent]:

        '''
        Create actionable ingress events from GitHub notifications API payloads.

        Returns:
        list[GitHubIngressEvent]: Actionable ingress events mapped from notifications.
        '''

        self._load_cursor()
        payloads = self._scan_notification_pages()
        notification_events = self._notification_mapper.map_notifications(payloads)
        self._annotate_scope_metadata(notification_events)
        enrichment_events = (
            self._scan_enrichment_events(notification_events)
            if self._include_enrichment
            else []
        )

        event_map: dict[str, GitHubIngressEvent] = {}
        for ingress_event in [*notification_events, *enrichment_events]:
            event_map[ingress_event.event_id] = ingress_event

        events = sorted(event_map.values(), key=lambda ingress_event: ingress_event.timestamp)
        if len(events) > 0:
            self._since = events[-1].timestamp
            if self._cursor_store is not None:
                self._cursor_store.set_cursor(self._cursor_key, self._since)

        return events

    def get_since_cursor(self) -> datetime | None:

        '''
        Create current scanner cursor timestamp for incremental notification scans.

        Returns:
        datetime | None: Last processed event timestamp cursor.
        '''

        return self._since

    def get_cursor_store(self) -> IngressCursorStore | None:

        '''
        Create current cursor store dependency for scanner runtime wiring checks.

        Returns:
        IngressCursorStore | None: Scanner cursor store dependency.
        '''

        return self._cursor_store

    def get_cursor_key(self) -> str:

        '''
        Create current cursor key used for durable scan checkpoints.

        Returns:
        str: Cursor source key identifier.
        '''

        return self._cursor_key


class InMemoryGitHubIngressScanner:
    def __init__(self, events: list[GitHubIngressEvent]) -> None:
        self._events = events

    def scan(self) -> list[GitHubIngressEvent]:

        '''
        Create scanned ingress event list from in-memory event buffer.

        Returns:
        list[GitHubIngressEvent]: Snapshot of ingress events.
        '''

        return list(self._events)


__all__ = [
    'GitHubIngressScanner',
    'GitHubNotificationScanner',
    'InMemoryGitHubIngressScanner',
]
