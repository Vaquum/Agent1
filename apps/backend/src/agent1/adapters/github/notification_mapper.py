from __future__ import annotations

from datetime import datetime
from datetime import timezone
import re
from collections.abc import Mapping
from collections.abc import Sequence

from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType

ENTITY_NUMBER_PATTERN = re.compile(r'/(issues|pulls)/(?P<number>\d+)$')


def _get_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value

    return ''


def _get_dict(payload: Mapping[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return dict(value)

    return {}


def _parse_timestamp(timestamp_value: str) -> datetime | None:
    if timestamp_value == '':
        return None

    normalized = timestamp_value.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _map_event_type(reason: str, entity_type: IngressEntityType) -> IngressEventType | None:
    if reason == 'mention':
        if entity_type == IngressEntityType.ISSUE:
            return IngressEventType.ISSUE_MENTION

        return IngressEventType.PR_MENTION

    if reason == 'assign' and entity_type == IngressEntityType.ISSUE:
        return IngressEventType.ISSUE_ASSIGNMENT

    if reason == 'comment' and entity_type == IngressEntityType.ISSUE:
        return IngressEventType.ISSUE_UPDATED

    if reason == 'review_requested' and entity_type == IngressEntityType.PR:
        return IngressEventType.PR_REVIEW_REQUESTED

    if reason == 'comment' and entity_type == IngressEntityType.PR:
        return IngressEventType.PR_REVIEW_COMMENT

    if reason == 'ci_activity' and entity_type == IngressEntityType.PR:
        return IngressEventType.PR_CI_FAILED

    if reason in {'author', 'state_change'} and entity_type == IngressEntityType.PR:
        return IngressEventType.PR_UPDATED

    return None


def _extract_entity_number(subject_url: str) -> int | None:
    match = ENTITY_NUMBER_PATTERN.search(subject_url)
    if match is None:
        return None

    return int(match.group('number'))


class GitHubNotificationMapper:
    def map_notification(self, notification_payload: Mapping[str, object]) -> GitHubIngressEvent | None:

        '''
        Create normalized ingress event from a GitHub notification payload.

        Args:
        notification_payload (Mapping[str, object]): Raw notification payload.

        Returns:
        GitHubIngressEvent | None: Mapped ingress event or None when payload is not actionable.
        '''

        subject = _get_dict(notification_payload, 'subject')
        repository_payload = _get_dict(notification_payload, 'repository')
        owner_payload = _get_dict(repository_payload, 'owner')

        subject_type = _get_string(subject, 'type')
        if subject_type == 'Issue':
            entity_type = IngressEntityType.ISSUE
        elif subject_type == 'PullRequest':
            entity_type = IngressEntityType.PR
        else:
            return None

        reason = _get_string(notification_payload, 'reason')
        event_type = _map_event_type(reason, entity_type)
        if event_type is None:
            return None

        subject_url = _get_string(subject, 'url')
        entity_number = _extract_entity_number(subject_url)
        if entity_number is None:
            return None

        event_id = _get_string(notification_payload, 'id')
        repository = _get_string(repository_payload, 'full_name')
        updated_at = _parse_timestamp(_get_string(notification_payload, 'updated_at'))
        if event_id == '' or repository == '' or updated_at is None:
            return None

        actor = _get_string(owner_payload, 'login')
        if actor == '':
            actor = 'unknown'

        details: dict[str, object] = {
            'reason': reason,
            'subject_type': subject_type,
            'subject_url': subject_url,
        }
        if event_type == IngressEventType.ISSUE_UPDATED:
            details['has_sufficient_context'] = True

        return GitHubIngressEvent(
            event_id=event_id,
            repository=repository,
            entity_number=entity_number,
            entity_type=entity_type,
            actor=actor,
            event_type=event_type,
            timestamp=updated_at.astimezone(timezone.utc),
            details=details,
        )

    def map_notifications(
        self,
        notification_payloads: Sequence[Mapping[str, object]],
    ) -> list[GitHubIngressEvent]:

        '''
        Create ingress event list from GitHub notifications payload list.

        Args:
        notification_payloads (Sequence[Mapping[str, object]]): Raw notifications payload list.

        Returns:
        list[GitHubIngressEvent]: Mapped actionable ingress events.
        '''

        mapped_events: list[GitHubIngressEvent] = []
        for payload in notification_payloads:
            mapped_event = self.map_notification(payload)
            if mapped_event is not None:
                mapped_events.append(mapped_event)

        return mapped_events


__all__ = ['GitHubNotificationMapper']
