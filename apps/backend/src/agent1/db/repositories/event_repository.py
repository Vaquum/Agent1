from __future__ import annotations

import hashlib
import json
from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.db.models import EventJournalModel


def _to_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def _to_canonical_payload_value(value: object) -> Any:
    if isinstance(value, datetime):
        return _to_utc_timestamp(value).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {
            str(key): _to_canonical_payload_value(payload_value)
            for key, payload_value in value.items()
        }
    if isinstance(value, list):
        return [_to_canonical_payload_value(payload_value) for payload_value in value]

    return value


def _compute_event_payload_hash(
    timestamp: datetime,
    environment: EnvironmentName,
    trace_id: str,
    job_id: str,
    entity_key: str,
    source: EventSource,
    event_type: EventType,
    status: EventStatus,
    details: dict[str, object],
    event_seq: int,
    prev_event_hash: str | None,
) -> str:
    payload = {
        'timestamp': _to_utc_timestamp(timestamp).isoformat(),
        'environment': environment.value,
        'trace_id': trace_id,
        'job_id': job_id,
        'entity_key': entity_key,
        'source': source.value,
        'event_type': event_type.value,
        'status': status.value,
        'details': _to_canonical_payload_value(details),
        'event_seq': event_seq,
        'prev_event_hash': prev_event_hash,
    }
    serialized_payload = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    )
    return hashlib.sha256(serialized_payload.encode('utf-8')).hexdigest()


def _is_alert_signal_event(model: EventJournalModel) -> bool:
    details = model.details
    action = details.get('action')
    alert_name = details.get('alert_name')
    return isinstance(action, str) and action == 'emit_alert_signal' and isinstance(alert_name, str)


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_event(self, event: AgentEvent) -> EventJournalModel:

        '''
        Create persisted event journal row from typed event contract.

        Args:
        event (AgentEvent): Typed event contract for journaling.

        Returns:
        EventJournalModel: Persisted event journal model.
        '''

        missing_chain_rows = (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.environment == event.environment)
            .filter(
                or_(
                    EventJournalModel.event_seq.is_(None),
                    EventJournalModel.payload_hash.is_(None),
                ),
            )
            .count()
        )
        if missing_chain_rows != 0:
            self.rebuild_event_chain(environment=event.environment)

        latest_model = (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.environment == event.environment)
            .filter(EventJournalModel.event_seq.isnot(None))
            .order_by(EventJournalModel.event_seq.desc())
            .with_for_update()
            .first()
        )
        next_event_seq = 1
        previous_event_hash: str | None = None
        if latest_model is not None and latest_model.event_seq is not None:
            next_event_seq = latest_model.event_seq + 1
            previous_event_hash = latest_model.payload_hash

        payload_hash = _compute_event_payload_hash(
            timestamp=event.timestamp,
            environment=event.environment,
            trace_id=event.trace_id,
            job_id=event.job_id,
            entity_key=event.entity_key,
            source=event.source,
            event_type=event.event_type,
            status=event.status,
            details=event.details,
            event_seq=next_event_seq,
            prev_event_hash=previous_event_hash,
        )
        model = EventJournalModel(
            timestamp=event.timestamp,
            environment=event.environment,
            event_seq=next_event_seq,
            prev_event_hash=previous_event_hash,
            payload_hash=payload_hash,
            trace_id=event.trace_id,
            job_id=event.job_id,
            entity_key=event.entity_key,
            source=event.source,
            event_type=event.event_type,
            status=event.status,
            details=event.details,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def list_recent_events(
        self,
        limit: int,
        offset: int = 0,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
        status: EventStatus | None = None,
    ) -> list[EventJournalModel]:

        '''
        Create recent event journal list ordered by descending timestamp.

        Args:
        limit (int): Maximum number of recent rows to return.
        offset (int): Pagination offset for recent rows.
        entity_key (str | None): Optional entity key filter.
        job_id (str | None): Optional job identifier filter.
        trace_id (str | None): Optional trace identifier filter.
        status (EventStatus | None): Optional event status filter.

        Returns:
        list[EventJournalModel]: Ordered recent event journal rows.
        '''

        query = self._session.query(EventJournalModel)
        if entity_key is not None and entity_key.strip() != '':
            query = query.filter(EventJournalModel.entity_key == entity_key.strip())
        if job_id is not None and job_id.strip() != '':
            query = query.filter(EventJournalModel.job_id == job_id.strip())
        if trace_id is not None and trace_id.strip() != '':
            query = query.filter(EventJournalModel.trace_id == trace_id.strip())
        if status is not None:
            query = query.filter(EventJournalModel.status == status)

        return query.order_by(EventJournalModel.timestamp.desc()).offset(offset).limit(limit).all()

    def count_events(
        self,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
        status: EventStatus | None = None,
    ) -> int:

        '''
        Create event journal row count for optional dashboard filters.

        Args:
        entity_key (str | None): Optional entity key filter.
        job_id (str | None): Optional job identifier filter.
        trace_id (str | None): Optional trace identifier filter.
        status (EventStatus | None): Optional event status filter.

        Returns:
        int: Event journal row count matching provided filters.
        '''

        query = self._session.query(EventJournalModel)
        if entity_key is not None and entity_key.strip() != '':
            query = query.filter(EventJournalModel.entity_key == entity_key.strip())
        if job_id is not None and job_id.strip() != '':
            query = query.filter(EventJournalModel.job_id == job_id.strip())
        if trace_id is not None and trace_id.strip() != '':
            query = query.filter(EventJournalModel.trace_id == trace_id.strip())
        if status is not None:
            query = query.filter(EventJournalModel.status == status)

        return query.count()

    def count_recent_failed_transition_events(
        self,
        window_start: datetime,
    ) -> int:

        '''
        Create count of recent blocked or error transition events.

        Args:
        window_start (datetime): Inclusive lower bound for event timestamps.

        Returns:
        int: Recent failed transition event count.
        '''

        return (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.timestamp >= window_start)
            .filter(EventJournalModel.event_type == EventType.STATE_TRANSITION)
            .filter(
                EventJournalModel.status.in_(
                    [
                        EventStatus.BLOCKED,
                        EventStatus.ERROR,
                    ],
                ),
            )
            .count()
        )

    def list_events_since(
        self,
        environment: EnvironmentName,
        window_start: datetime,
        source: EventSource | None = None,
    ) -> list[EventJournalModel]:

        '''
        Create environment-scoped event journal rows since one inclusive timestamp.

        Args:
        environment (EnvironmentName): Runtime environment value.
        window_start (datetime): Inclusive lower bound for event timestamps.
        source (EventSource | None): Optional event source filter.

        Returns:
        list[EventJournalModel]: Ordered event journal rows since timestamp.
        '''

        query = (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.environment == environment)
            .filter(EventJournalModel.timestamp >= window_start)
        )
        if source is not None:
            query = query.filter(EventJournalModel.source == source)

        return query.order_by(EventJournalModel.timestamp.asc()).all()

    def rebuild_event_chain(self, environment: EnvironmentName | None = None) -> int:

        '''
        Create deterministic chain values for existing event journal rows.

        Args:
        environment (EnvironmentName | None): Optional environment filter.

        Returns:
        int: Number of rows rebuilt for chain integrity.
        '''

        query = self._session.query(EventJournalModel)
        if environment is not None:
            query = query.filter(EventJournalModel.environment == environment)

        models = query.order_by(
            EventJournalModel.environment.asc(),
            EventJournalModel.timestamp.asc(),
            EventJournalModel.id.asc(),
        ).with_for_update().all()
        chain_state_by_environment: dict[EnvironmentName, tuple[int, str | None]] = {}
        rebuilt_count = 0
        for model in models:
            current_state = chain_state_by_environment.get(model.environment, (0, None))
            event_seq = current_state[0] + 1
            prev_event_hash = current_state[1]
            payload_hash = _compute_event_payload_hash(
                timestamp=model.timestamp,
                environment=model.environment,
                trace_id=model.trace_id,
                job_id=model.job_id,
                entity_key=model.entity_key,
                source=model.source,
                event_type=model.event_type,
                status=model.status,
                details=model.details,
                event_seq=event_seq,
                prev_event_hash=prev_event_hash,
            )
            model.event_seq = event_seq
            model.prev_event_hash = prev_event_hash
            model.payload_hash = payload_hash
            chain_state_by_environment[model.environment] = (event_seq, payload_hash)
            rebuilt_count += 1

        self._session.flush()
        return rebuilt_count

    def verify_event_chain(self, environment: EnvironmentName | None = None) -> list[str]:

        '''
        Create tamper-evident chain validation findings for event journal rows.

        Args:
        environment (EnvironmentName | None): Optional environment filter.

        Returns:
        list[str]: Human-readable chain validation findings.
        '''

        query = self._session.query(EventJournalModel)
        if environment is not None:
            query = query.filter(EventJournalModel.environment == environment)

        models = query.order_by(
            EventJournalModel.environment.asc(),
            EventJournalModel.timestamp.asc(),
            EventJournalModel.id.asc(),
        ).all()
        findings: list[str] = []
        expected_state_by_environment: dict[EnvironmentName, tuple[int, str | None]] = {}
        for model in models:
            expected_state = expected_state_by_environment.get(model.environment, (1, None))
            expected_event_seq = expected_state[0]
            expected_prev_hash = expected_state[1]
            if model.event_seq != expected_event_seq:
                findings.append(
                    'Event chain sequence mismatch '
                    f'(id={model.id}, environment={model.environment.value}, '
                    f'expected_seq={expected_event_seq}, actual_seq={model.event_seq})'
                )
            if model.prev_event_hash != expected_prev_hash:
                findings.append(
                    'Event chain previous-hash mismatch '
                    f'(id={model.id}, environment={model.environment.value}, '
                    f'expected_prev_hash={expected_prev_hash}, actual_prev_hash={model.prev_event_hash})'
                )

            if model.event_seq is None:
                findings.append(
                    'Event chain sequence missing '
                    f'(id={model.id}, environment={model.environment.value})'
                )
            if model.payload_hash is None:
                findings.append(
                    'Event chain payload hash missing '
                    f'(id={model.id}, environment={model.environment.value})'
                )
            if model.event_seq is not None and model.payload_hash is not None:
                recomputed_payload_hash = _compute_event_payload_hash(
                    timestamp=model.timestamp,
                    environment=model.environment,
                    trace_id=model.trace_id,
                    job_id=model.job_id,
                    entity_key=model.entity_key,
                    source=model.source,
                    event_type=model.event_type,
                    status=model.status,
                    details=model.details,
                    event_seq=model.event_seq,
                    prev_event_hash=model.prev_event_hash,
                )
                if model.payload_hash != recomputed_payload_hash:
                    findings.append(
                        'Event chain payload hash mismatch '
                        f'(id={model.id}, environment={model.environment.value})'
                    )

            expected_state_by_environment[model.environment] = (
                expected_event_seq + 1,
                model.payload_hash,
            )

        return findings

    def list_recent_anomaly_events(
        self,
        limit: int,
        offset: int = 0,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[EventJournalModel]:

        '''
        Create recent alert-signal anomaly event rows ordered by descending timestamp.

        Args:
        limit (int): Maximum number of rows to return.
        offset (int): Pagination offset for rows.
        entity_key (str | None): Optional entity key filter.
        job_id (str | None): Optional job identifier filter.
        trace_id (str | None): Optional trace identifier filter.

        Returns:
        list[EventJournalModel]: Ordered anomaly event rows.
        '''

        query = (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.source == EventSource.POLICY)
            .filter(EventJournalModel.event_type == EventType.API_CALL)
            .filter(EventJournalModel.status == EventStatus.ERROR)
        )
        if entity_key is not None and entity_key.strip() != '':
            query = query.filter(EventJournalModel.entity_key == entity_key.strip())
        if job_id is not None and job_id.strip() != '':
            query = query.filter(EventJournalModel.job_id == job_id.strip())
        if trace_id is not None and trace_id.strip() != '':
            query = query.filter(EventJournalModel.trace_id == trace_id.strip())

        models = query.order_by(EventJournalModel.timestamp.desc()).all()
        anomaly_models = [model for model in models if _is_alert_signal_event(model)]
        return anomaly_models[offset: offset + limit]

    def count_anomaly_events(
        self,
        entity_key: str | None = None,
        job_id: str | None = None,
        trace_id: str | None = None,
    ) -> int:

        '''
        Create anomaly event row count for optional dashboard filters.

        Args:
        entity_key (str | None): Optional entity key filter.
        job_id (str | None): Optional job identifier filter.
        trace_id (str | None): Optional trace identifier filter.

        Returns:
        int: Anomaly event row count matching filters.
        '''

        query = (
            self._session.query(EventJournalModel)
            .filter(EventJournalModel.source == EventSource.POLICY)
            .filter(EventJournalModel.event_type == EventType.API_CALL)
            .filter(EventJournalModel.status == EventStatus.ERROR)
        )
        if entity_key is not None and entity_key.strip() != '':
            query = query.filter(EventJournalModel.entity_key == entity_key.strip())
        if job_id is not None and job_id.strip() != '':
            query = query.filter(EventJournalModel.job_id == job_id.strip())
        if trace_id is not None and trace_id.strip() != '':
            query = query.filter(EventJournalModel.trace_id == trace_id.strip())

        models = query.all()
        return len([model for model in models if _is_alert_signal_event(model)])


__all__ = ['EventRepository']
