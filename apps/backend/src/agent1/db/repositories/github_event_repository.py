from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import EnvironmentName
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressOrderingDecision
from agent1.core.ingress_contracts import PersistedIngressEvent
from agent1.db.models import GitHubEventModel
from agent1.db.models import IngressEntityCursorModel

STALE_REASON_OLDER_TIMESTAMP = 'older_source_timestamp'
STALE_REASON_TIE_BREAKER = 'source_timestamp_tie_breaker'
STALE_REASON_DUPLICATE_EVENT_ID = 'duplicate_source_event_id'


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for ingress persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def _is_newer_than_high_water(
    source_timestamp: datetime,
    source_event_id: str,
    high_water_source_timestamp: datetime,
    high_water_source_event_id: str,
) -> bool:
    if source_timestamp > high_water_source_timestamp:
        return True

    if source_timestamp < high_water_source_timestamp:
        return False

    return source_event_id > high_water_source_event_id


def _build_stale_reason(
    source_timestamp: datetime,
    source_event_id: str,
    high_water_source_timestamp: datetime,
    high_water_source_event_id: str,
) -> str:
    if source_timestamp < high_water_source_timestamp:
        return STALE_REASON_OLDER_TIMESTAMP

    if source_event_id == high_water_source_event_id:
        return STALE_REASON_DUPLICATE_EVENT_ID

    return STALE_REASON_TIE_BREAKER


class GitHubEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_ingress_event(
        self,
        ingress_event: GitHubIngressEvent,
        environment: EnvironmentName,
        received_at: datetime | None = None,
    ) -> PersistedIngressEvent:

        '''
        Create persisted ingress event row and deterministic high-water ordering decision.

        Args:
        ingress_event (GitHubIngressEvent): Raw GitHub ingress event payload.
        environment (EnvironmentName): Runtime environment value.
        received_at (datetime | None): Optional receive timestamp override.

        Returns:
        PersistedIngressEvent: Persisted ingress event ordering decision payload.
        '''

        normalized_source_timestamp = _ensure_utc_timestamp(ingress_event.timestamp)
        normalized_received_at = _utc_now() if received_at is None else _ensure_utc_timestamp(received_at)
        source_timestamp_or_seq = str(ingress_event.details.get('source_timestamp_or_seq', '')).strip()
        if source_timestamp_or_seq == '':
            source_timestamp_or_seq = normalized_source_timestamp.isoformat()

        entity_key = f'{ingress_event.repository}#{ingress_event.entity_number}'
        cursor = (
            self._session.query(IngressEntityCursorModel)
            .filter(IngressEntityCursorModel.environment == environment)
            .filter(IngressEntityCursorModel.entity_key == entity_key)
            .one_or_none()
        )
        ordering_decision = IngressOrderingDecision.ACCEPTED
        stale_reason: str | None = None
        if cursor is None:
            cursor = IngressEntityCursorModel(
                environment=environment,
                entity_key=entity_key,
                high_water_source_timestamp=normalized_source_timestamp,
                high_water_source_event_id=ingress_event.event_id,
                updated_at=normalized_received_at,
            )
            self._session.add(cursor)
        else:
            cursor_source_timestamp = _ensure_utc_timestamp(cursor.high_water_source_timestamp)
            if _is_newer_than_high_water(
                source_timestamp=normalized_source_timestamp,
                source_event_id=ingress_event.event_id,
                high_water_source_timestamp=cursor_source_timestamp,
                high_water_source_event_id=cursor.high_water_source_event_id,
            ):
                cursor.high_water_source_timestamp = normalized_source_timestamp
                cursor.high_water_source_event_id = ingress_event.event_id
                cursor.updated_at = normalized_received_at
            else:
                ordering_decision = IngressOrderingDecision.STALE
                stale_reason = _build_stale_reason(
                    source_timestamp=normalized_source_timestamp,
                    source_event_id=ingress_event.event_id,
                    high_water_source_timestamp=cursor_source_timestamp,
                    high_water_source_event_id=cursor.high_water_source_event_id,
                )

        model = GitHubEventModel(
            source_event_id=ingress_event.event_id,
            source_timestamp_or_seq=source_timestamp_or_seq,
            source_timestamp=normalized_source_timestamp,
            received_at=normalized_received_at,
            environment=environment,
            repository=ingress_event.repository,
            entity_number=ingress_event.entity_number,
            entity_key=entity_key,
            actor=ingress_event.actor,
            ingress_event_type=ingress_event.event_type.value,
            ordering_decision=ordering_decision.value,
            is_stale=ordering_decision == IngressOrderingDecision.STALE,
            stale_reason=stale_reason,
            details=ingress_event.details,
        )
        self._session.add(model)
        self._session.flush()

        return PersistedIngressEvent(
            source_event_id=model.source_event_id,
            entity_key=model.entity_key,
            source_timestamp_or_seq=model.source_timestamp_or_seq,
            received_at=model.received_at,
            ordering_decision=ordering_decision,
            stale_reason=stale_reason,
        )


__all__ = [
    'GitHubEventRepository',
    'STALE_REASON_DUPLICATE_EVENT_ID',
    'STALE_REASON_OLDER_TIMESTAMP',
    'STALE_REASON_TIE_BREAKER',
]
