from __future__ import annotations

from datetime import datetime
from typing import Protocol

from agent1.adapters.github.check_run_mapper import GitHubCheckRunMapper
from agent1.adapters.github.client import GitHubApiClient
from agent1.adapters.github.client import UrlLibGitHubApiClient
from agent1.adapters.github.notification_mapper import GitHubNotificationMapper
from agent1.adapters.github.timeline_mapper import GitHubTimelineMapper
from agent1.config.settings import get_settings
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.services.ingress_cursor_store import IngressCursorStore
from agent1.core.services.persistence_service import PersistenceService


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
    state_value = payload.get('state')
    if isinstance(state_value, str) and state_value.strip() != '':
        metadata['resource_state'] = state_value.strip()
    merged_value = payload.get('merged')
    if isinstance(merged_value, bool):
        metadata['is_merged'] = merged_value
    user_value = payload.get('user')
    if isinstance(user_value, dict):
        author_login_value = user_value.get('login')
        if isinstance(author_login_value, str) and author_login_value.strip() != '':
            metadata['author_login'] = author_login_value.strip()
    head_value = payload.get('head')
    if isinstance(head_value, dict):
        ref_value = head_value.get('ref')
        if isinstance(ref_value, str) and ref_value != '':
            metadata['head_ref'] = ref_value

    return metadata


def _parse_pull_entity_key(entity_key: str) -> tuple[str, int] | None:
    if '#' not in entity_key:
        return None

    repository, number_value = entity_key.rsplit('#', 1)
    repository = repository.strip()
    number_value = number_value.strip()
    if repository == '' or number_value == '' or number_value.isdigit() is False:
        return None

    return repository, int(number_value)


def _parse_iso8601_timestamp(timestamp_value: str) -> datetime | None:
    if timestamp_value.strip() == '':
        return None

    try:
        return datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
    except ValueError:
        return None


def _parse_payload_timestamp(payload: dict[str, object]) -> datetime | None:
    created_at_value = payload.get('created_at')
    if isinstance(created_at_value, str):
        parsed_created_at = _parse_iso8601_timestamp(created_at_value)
        if parsed_created_at is not None:
            return parsed_created_at

    submitted_at_value = payload.get('submitted_at')
    if isinstance(submitted_at_value, str):
        return _parse_iso8601_timestamp(submitted_at_value)

    return None


def _select_latest_payload(
    payloads: list[dict[str, object]],
    github_user: str,
    actor_field: str,
) -> dict[str, object] | None:
    latest_payload: dict[str, object] | None = None
    latest_timestamp: datetime | None = None
    latest_payload_id = -1

    for payload in payloads:
        actor_payload = payload.get(actor_field)
        actor_value = ''
        if isinstance(actor_payload, dict):
            actor_login_value = actor_payload.get('login')
            if isinstance(actor_login_value, str):
                actor_value = actor_login_value.strip().lower()
        if actor_value != '' and actor_value == github_user:
            continue

        parsed_timestamp = _parse_payload_timestamp(payload)
        if parsed_timestamp is None:
            continue

        payload_id_value = payload.get('id')
        payload_id = payload_id_value if isinstance(payload_id_value, int) else -1
        if latest_timestamp is None:
            latest_payload = payload
            latest_timestamp = parsed_timestamp
            latest_payload_id = payload_id
            continue

        if parsed_timestamp > latest_timestamp:
            latest_payload = payload
            latest_timestamp = parsed_timestamp
            latest_payload_id = payload_id
            continue

        if parsed_timestamp == latest_timestamp and payload_id > latest_payload_id:
            latest_payload = payload
            latest_timestamp = parsed_timestamp
            latest_payload_id = payload_id

    return latest_payload


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
        environment: EnvironmentName = EnvironmentName.DEV,
        persistence_service: PersistenceService | None = None,
        github_user: str = '',
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
        self._environment = environment
        self._persistence_service = persistence_service or PersistenceService()
        resolved_github_user = github_user.strip().lower()
        if resolved_github_user == '':
            resolved_github_user = get_settings().github_user.strip().lower()
        self._github_user = resolved_github_user

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
            review_comment_payloads = self._github_client.fetch_pull_request_review_comments(
                repository=notification_event.repository,
                pull_number=notification_event.entity_number,
            )
            mapped_review_comment_events = self._map_review_comment_enrichment_events(
                repository=notification_event.repository,
                pull_number=notification_event.entity_number,
                review_comment_payloads=review_comment_payloads,
                event_seed=notification_event.event_id,
                job_kind_hint=JobKind.PR_REVIEWER.value,
            )
            for enrichment_event in [*mapped_timeline_events, *mapped_check_events]:
                enrichment_event.details.update(
                    {
                        'label_names': notification_event.details.get('label_names', []),
                        'head_ref': notification_event.details.get('head_ref', ''),
                    }
                )
            for review_comment_event in mapped_review_comment_events:
                review_comment_event.details.update(
                    {
                        'label_names': notification_event.details.get('label_names', []),
                        'head_ref': notification_event.details.get('head_ref', ''),
                    }
                )

            enrichment_events.extend(mapped_timeline_events)
            enrichment_events.extend(mapped_check_events)
            enrichment_events.extend(mapped_review_comment_events)

        return enrichment_events

    def _map_review_comment_enrichment_events(
        self,
        repository: str,
        pull_number: int,
        review_comment_payloads: list[dict[str, object]],
        event_seed: str,
        job_kind_hint: str | None,
    ) -> list[GitHubIngressEvent]:
        mapped_events: list[GitHubIngressEvent] = []
        for index, review_comment_payload in enumerate(review_comment_payloads):
            in_reply_to_id = review_comment_payload.get('in_reply_to_id')
            if isinstance(in_reply_to_id, int) is False:
                continue

            review_comment_id = review_comment_payload.get('id')
            event_id_suffix = str(review_comment_id) if review_comment_id is not None else str(index)
            created_at = review_comment_payload.get('created_at')
            timestamp = (
                _parse_iso8601_timestamp(created_at)
                if isinstance(created_at, str)
                else None
            )
            if timestamp is None:
                continue

            user_payload = review_comment_payload.get('user')
            actor = 'unknown'
            if isinstance(user_payload, dict):
                actor_value = user_payload.get('login')
                if isinstance(actor_value, str) and actor_value.strip() != '':
                    actor = actor_value.strip()
            if self._github_user != '' and actor.strip().lower() == self._github_user:
                continue

            path = review_comment_payload.get('path')
            normalized_path = path if isinstance(path, str) else ''
            line_value = review_comment_payload.get('line')
            normalized_line: int | None = line_value if isinstance(line_value, int) else None
            if normalized_line is None:
                original_line_value = review_comment_payload.get('original_line')
                if isinstance(original_line_value, int):
                    normalized_line = original_line_value

            side_value = review_comment_payload.get('side')
            normalized_side = side_value if isinstance(side_value, str) else ''
            node_id_value = review_comment_payload.get('node_id')
            normalized_node_id = node_id_value if isinstance(node_id_value, str) else ''
            normalized_review_comment_id = (
                review_comment_id if isinstance(review_comment_id, int) else None
            )
            is_review_thread_comment = (
                normalized_review_comment_id is not None
                and normalized_path != ''
                and normalized_line is not None
                and normalized_side != ''
            )
            details: dict[str, object] = {
                'timeline_event_name': 'review_comment',
                'review_comment_id': normalized_review_comment_id,
                'thread_id': normalized_node_id,
                'path': normalized_path,
                'line': normalized_line,
                'side': normalized_side,
                'is_review_thread_comment': is_review_thread_comment,
                'pull_request_review_id': review_comment_payload.get('pull_request_review_id'),
                'in_reply_to_id': in_reply_to_id,
            }
            if job_kind_hint is not None:
                details['job_kind_hint'] = job_kind_hint

            mapped_events.append(
                GitHubIngressEvent(
                    event_id=f"{event_seed}:review_comment:{event_id_suffix}",
                    repository=repository,
                    entity_number=pull_number,
                    entity_type=IngressEntityType.PR,
                    actor=actor,
                    event_type=IngressEventType.PR_REVIEW_COMMENT,
                    timestamp=timestamp,
                    details=details,
                )
            )

        return mapped_events

    def _annotate_scope_metadata(self, notification_events: list[GitHubIngressEvent]) -> None:
        for notification_event in notification_events:
            if notification_event.entity_type == IngressEntityType.PR:
                pull_payload = self._github_client.fetch_pull_request(
                    repository=notification_event.repository,
                    pull_number=notification_event.entity_number,
                )
                pull_scope_metadata = _extract_scope_metadata(pull_payload)
                notification_event.details.update(
                    {
                        'label_names': pull_scope_metadata.get('label_names', []),
                        'head_ref': pull_scope_metadata.get('head_ref', ''),
                        'pull_state': pull_scope_metadata.get('resource_state', ''),
                        'pull_is_merged': pull_scope_metadata.get('is_merged', False),
                        'pull_author_login': pull_scope_metadata.get('author_login', ''),
                    }
                )
                continue

            issue_payload = self._github_client.fetch_issue(
                repository=notification_event.repository,
                issue_number=notification_event.entity_number,
            )
            issue_scope_metadata = _extract_scope_metadata(issue_payload)
            notification_event.details.update(
                {
                    'label_names': issue_scope_metadata.get('label_names', []),
                    'issue_state': issue_scope_metadata.get('resource_state', ''),
                    'issue_author_login': issue_scope_metadata.get('author_login', ''),
                }
            )

    def _scan_reviewer_follow_up_events(self) -> list[GitHubIngressEvent]:
        reviewer_jobs = self._persistence_service.list_jobs_by_kind_and_states(
            kind=JobKind.PR_REVIEWER,
            states=[JobState.AWAITING_HUMAN_FEEDBACK],
            limit=200,
        )
        follow_up_events: list[GitHubIngressEvent] = []
        for reviewer_job in reviewer_jobs:
            parsed_entity = _parse_pull_entity_key(reviewer_job.entity_key)
            if parsed_entity is None:
                continue

            repository, pull_number = parsed_entity
            mapped_timeline_events: list[GitHubIngressEvent] = []
            timeline_payloads = self._github_client.fetch_pull_request_timeline(
                repository=repository,
                pull_number=pull_number,
            )
            committed_payloads = [
                timeline_payload
                for timeline_payload in timeline_payloads
                if timeline_payload.get('event') == 'committed'
            ]
            if len(committed_payloads) != 0:
                committed_payloads = committed_payloads[-1:]
                mapped_timeline_events = self._timeline_mapper.map_timeline_events(
                    repository=repository,
                    pull_number=pull_number,
                    timeline_payloads=committed_payloads,
                    event_seed=f"watcher:{reviewer_job.job_id}",
                    job_kind_hint=JobKind.PR_REVIEWER.value,
                )

            review_comment_payloads = self._github_client.fetch_pull_request_review_comments(
                repository=repository,
                pull_number=pull_number,
            )
            thread_reply_payloads = [
                payload
                for payload in review_comment_payloads
                if isinstance(payload.get('in_reply_to_id'), int)
            ]
            latest_thread_payload = _select_latest_payload(
                payloads=thread_reply_payloads,
                github_user=self._github_user,
                actor_field='user',
            )
            mapped_review_comment_events = (
                self._map_review_comment_enrichment_events(
                    repository=repository,
                    pull_number=pull_number,
                    review_comment_payloads=[latest_thread_payload],
                    event_seed=f"watcher:{reviewer_job.job_id}",
                    job_kind_hint=JobKind.PR_REVIEWER.value,
                )
                if latest_thread_payload is not None
                else []
            )
            if len(mapped_timeline_events) == 0 and len(mapped_review_comment_events) == 0:
                continue

            pull_payload = self._github_client.fetch_pull_request(
                repository=repository,
                pull_number=pull_number,
            )
            pull_scope_metadata = _extract_scope_metadata(pull_payload)
            for mapped_event in [*mapped_timeline_events, *mapped_review_comment_events]:
                mapped_event.details.update(
                    {
                        'label_names': pull_scope_metadata.get('label_names', []),
                        'head_ref': pull_scope_metadata.get('head_ref', ''),
                        'pull_state': pull_scope_metadata.get('resource_state', ''),
                        'pull_is_merged': pull_scope_metadata.get('is_merged', False),
                        'pull_author_login': pull_scope_metadata.get('author_login', ''),
                    }
                )
            follow_up_events.extend(mapped_timeline_events)
            follow_up_events.extend(mapped_review_comment_events)

        return follow_up_events

    def _scan_author_follow_up_events(self) -> list[GitHubIngressEvent]:
        author_jobs = self._persistence_service.list_jobs_by_kind_and_states(
            kind=JobKind.PR_AUTHOR,
            states=[JobState.AWAITING_HUMAN_FEEDBACK],
            limit=200,
        )
        follow_up_events: list[GitHubIngressEvent] = []
        for author_job in author_jobs:
            parsed_entity = _parse_pull_entity_key(author_job.entity_key)
            if parsed_entity is None:
                continue

            repository, pull_number = parsed_entity
            timeline_payloads = self._github_client.fetch_pull_request_timeline(
                repository=repository,
                pull_number=pull_number,
            )
            comment_payloads = [
                timeline_payload
                for timeline_payload in timeline_payloads
                if timeline_payload.get('event') in {'commented', 'reviewed'}
            ]
            latest_comment_payload = _select_latest_payload(
                payloads=comment_payloads,
                github_user=self._github_user,
                actor_field='actor',
            )
            mapped_follow_up_events = self._timeline_mapper.map_timeline_events(
                repository=repository,
                pull_number=pull_number,
                timeline_payloads=[latest_comment_payload] if latest_comment_payload is not None else [],
                event_seed=f"watcher:{author_job.job_id}",
                job_kind_hint=JobKind.PR_AUTHOR.value,
            )
            check_run_payloads = self._github_client.fetch_pull_request_check_runs(
                repository=repository,
                pull_number=pull_number,
            )
            mapped_check_events = self._check_run_mapper.map_check_runs(
                repository=repository,
                pull_number=pull_number,
                check_run_payloads=check_run_payloads,
                event_seed=f"watcher:{author_job.job_id}",
            )
            if len(mapped_follow_up_events) == 0 and len(mapped_check_events) == 0:
                continue

            pull_payload = self._github_client.fetch_pull_request(
                repository=repository,
                pull_number=pull_number,
            )
            pull_scope_metadata = _extract_scope_metadata(pull_payload)
            for mapped_event in [*mapped_follow_up_events, *mapped_check_events]:
                mapped_event.details.update(
                    {
                        'label_names': pull_scope_metadata.get('label_names', []),
                        'head_ref': pull_scope_metadata.get('head_ref', ''),
                        'pull_state': pull_scope_metadata.get('resource_state', ''),
                        'pull_is_merged': pull_scope_metadata.get('is_merged', False),
                        'pull_author_login': pull_scope_metadata.get('author_login', ''),
                    }
                )
            follow_up_events.extend(mapped_follow_up_events)
            follow_up_events.extend(mapped_check_events)

        return follow_up_events

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
        reviewer_follow_up_events = self._scan_reviewer_follow_up_events()
        author_follow_up_events = self._scan_author_follow_up_events()

        event_map: dict[str, GitHubIngressEvent] = {}
        for ingress_event in [
            *notification_events,
            *enrichment_events,
            *reviewer_follow_up_events,
            *author_follow_up_events,
        ]:
            event_map[ingress_event.event_id] = ingress_event

        events = sorted(
            event_map.values(),
            key=lambda ingress_event: (ingress_event.timestamp, ingress_event.event_id),
        )
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
