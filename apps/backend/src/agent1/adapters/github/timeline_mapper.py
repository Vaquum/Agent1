from __future__ import annotations

from datetime import datetime
from datetime import timezone
from collections.abc import Mapping
from collections.abc import Sequence

from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType


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


def _get_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int):
        return value

    return None


def _parse_timestamp(*timestamp_values: str) -> datetime | None:
    for timestamp_value in timestamp_values:
        if timestamp_value == '':
            continue

        normalized = timestamp_value.replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(normalized).astimezone(timezone.utc)
        except ValueError:
            continue

    return None


def _resolve_event_id_suffix(
    timeline_payload: Mapping[str, object],
    timeline_event_name: str,
    index: int,
) -> str:
    timeline_id = timeline_payload.get('id')
    if timeline_id is not None:
        return str(timeline_id)

    if timeline_event_name == 'committed':
        commit_sha = _get_string(timeline_payload, 'sha')
        if commit_sha != '':
            return f"sha:{commit_sha}"

    return str(index)


def _build_details(
    timeline_payload: Mapping[str, object],
    timeline_event_name: str,
    job_kind_hint: str | None,
) -> dict[str, object]:
    details: dict[str, object] = {
        'timeline_event_name': timeline_event_name,
    }
    if job_kind_hint is not None:
        details['job_kind_hint'] = job_kind_hint
    if timeline_event_name == 'committed':
        details['requires_follow_up'] = True
        details['commit_sha'] = _get_string(timeline_payload, 'sha')
        return details

    if timeline_event_name not in {'commented', 'reviewed'}:
        return details

    review_comment_id = _get_int(timeline_payload, 'id')
    path = _get_string(timeline_payload, 'path')
    line = _get_int(timeline_payload, 'line')
    if line is None:
        line = _get_int(timeline_payload, 'original_line')
    side = _get_string(timeline_payload, 'side')
    thread_id = _get_string(timeline_payload, 'node_id')
    is_review_thread_comment = (
        review_comment_id is not None
        and path != ''
        and line is not None
        and side != ''
    )
    details.update(
        {
            'review_comment_id': review_comment_id,
            'thread_id': thread_id,
            'path': path,
            'line': line,
            'side': side,
            'is_review_thread_comment': is_review_thread_comment,
            'pull_request_review_id': _get_int(timeline_payload, 'pull_request_review_id'),
        }
    )
    return details


def _map_timeline_event_type(timeline_event_name: str) -> IngressEventType | None:
    if timeline_event_name == 'review_requested':
        return IngressEventType.PR_REVIEW_REQUESTED

    if timeline_event_name in {'commented', 'reviewed'}:
        return IngressEventType.PR_REVIEW_COMMENT

    if timeline_event_name in {'committed'}:
        return IngressEventType.PR_UPDATED

    return None


class GitHubTimelineMapper:
    def map_timeline_events(
        self,
        repository: str,
        pull_number: int,
        timeline_payloads: Sequence[Mapping[str, object]],
        event_seed: str,
        job_kind_hint: str | None = None,
    ) -> list[GitHubIngressEvent]:

        '''
        Create ingress events from pull request timeline payload list.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.
        timeline_payloads (Sequence[Mapping[str, object]]): Timeline payloads.
        event_seed (str): Upstream event seed for deterministic IDs.
        job_kind_hint (str | None): Optional job kind hint for downstream normalization.

        Returns:
        list[GitHubIngressEvent]: Timeline-derived ingress events.
        '''

        mapped_events: list[GitHubIngressEvent] = []
        for index, timeline_payload in enumerate(timeline_payloads):
            timeline_event_name = _get_string(timeline_payload, 'event')
            ingress_event_type = _map_timeline_event_type(timeline_event_name)
            if ingress_event_type is None:
                continue

            event_id_suffix = _resolve_event_id_suffix(
                timeline_payload=timeline_payload,
                timeline_event_name=timeline_event_name,
                index=index,
            )
            timestamp = _parse_timestamp(
                _get_string(timeline_payload, 'created_at'),
                _get_string(timeline_payload, 'submitted_at'),
                _get_string(_get_dict(timeline_payload, 'author'), 'date'),
                _get_string(_get_dict(timeline_payload, 'committer'), 'date'),
            )
            if timestamp is None:
                continue

            actor_payload = _get_dict(timeline_payload, 'actor')
            actor = _get_string(actor_payload, 'login')
            if actor == '':
                actor = 'unknown'

            mapped_events.append(
                GitHubIngressEvent(
                    event_id=f"{event_seed}:timeline:{event_id_suffix}",
                    repository=repository,
                    entity_number=pull_number,
                    entity_type=IngressEntityType.PR,
                    actor=actor,
                    event_type=ingress_event_type,
                    timestamp=timestamp,
                    details=_build_details(
                        timeline_payload=timeline_payload,
                        timeline_event_name=timeline_event_name,
                        job_kind_hint=job_kind_hint,
                    ),
                )
            )

        return mapped_events


__all__ = ['GitHubTimelineMapper']
