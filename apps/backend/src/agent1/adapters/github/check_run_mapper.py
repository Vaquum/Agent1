from __future__ import annotations

from datetime import datetime
from datetime import timezone
from collections.abc import Mapping
from collections.abc import Sequence

from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType

FAILED_CONCLUSIONS = {
    'action_required',
    'cancelled',
    'failure',
    'startup_failure',
    'timed_out',
}


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


class GitHubCheckRunMapper:
    def map_check_runs(
        self,
        repository: str,
        pull_number: int,
        check_run_payloads: Sequence[Mapping[str, object]],
        event_seed: str,
    ) -> list[GitHubIngressEvent]:

        '''
        Create CI failure ingress events from pull request check-run payloads.

        Args:
        repository (str): Repository full name in owner/repo format.
        pull_number (int): Pull request number.
        check_run_payloads (Sequence[Mapping[str, object]]): Check-run payload list.
        event_seed (str): Upstream event seed for deterministic IDs.

        Returns:
        list[GitHubIngressEvent]: Check-run-derived ingress events.
        '''

        mapped_events: list[GitHubIngressEvent] = []
        for index, check_run_payload in enumerate(check_run_payloads):
            conclusion = _get_string(check_run_payload, 'conclusion')
            if conclusion not in FAILED_CONCLUSIONS:
                continue

            check_run_id = check_run_payload.get('id')
            event_id_suffix = str(check_run_id) if check_run_id is not None else str(index)
            timestamp = _parse_timestamp(
                _get_string(check_run_payload, 'completed_at'),
                _get_string(check_run_payload, 'started_at'),
                _get_string(check_run_payload, 'created_at'),
            )
            if timestamp is None:
                continue

            app_payload = _get_dict(check_run_payload, 'app')
            actor = _get_string(app_payload, 'slug')
            if actor == '':
                actor = _get_string(app_payload, 'name')
            if actor == '':
                actor = 'github-checks'

            mapped_events.append(
                GitHubIngressEvent(
                    event_id=f"{event_seed}:check:{event_id_suffix}",
                    repository=repository,
                    entity_number=pull_number,
                    entity_type=IngressEntityType.PR,
                    actor=actor,
                    event_type=IngressEventType.PR_CI_FAILED,
                    timestamp=timestamp,
                    details={
                        'check_name': _get_string(check_run_payload, 'name'),
                        'status': _get_string(check_run_payload, 'status'),
                        'conclusion': conclusion,
                    },
                )
            )

        return mapped_events


__all__ = ['GitHubCheckRunMapper']
