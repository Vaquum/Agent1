from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EntityType
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxStatus
from agent1.core.contracts import RuntimeMode
from agent1.core.contracts import WatcherStatus
from agent1.db.base import Base

MAX_ID_LENGTH = 120
MAX_ENTITY_KEY_LENGTH = 255
MAX_EVENT_TYPE_LENGTH = 80
MAX_STALE_REASON_LENGTH = 255


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for persistence defaults.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


class JobModel(Base):
    __tablename__ = 'jobs'
    __table_args__ = (
        UniqueConstraint(
            'environment',
            'idempotency_key',
            name='uq_jobs_environment_idempotency_key',
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), unique=True, nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    kind: Mapped[JobKind] = mapped_column(Enum(JobKind, native_enum=False), nullable=False)
    state: Mapped[JobState] = mapped_column(Enum(JobState, native_enum=False), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
    )
    mode: Mapped[RuntimeMode] = mapped_column(Enum(RuntimeMode, native_enum=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    transitions: Mapped[list['JobTransitionModel']] = relationship(back_populates='job')


class JobTransitionModel(Base):
    __tablename__ = 'job_transitions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(MAX_ID_LENGTH),
        ForeignKey('jobs.job_id'),
        nullable=False,
        index=True,
    )
    from_state: Mapped[JobState] = mapped_column(Enum(JobState, native_enum=False), nullable=False)
    to_state: Mapped[JobState] = mapped_column(Enum(JobState, native_enum=False), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    transition_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    job: Mapped[JobModel] = relationship(back_populates='transitions')


class EntityModel(Base):
    __tablename__ = 'entities'
    __table_args__ = (
        UniqueConstraint(
            'environment',
            'entity_key',
            name='uq_entities_environment_entity_key',
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    repository: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    entity_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType, native_enum=False), nullable=False, index=True)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
        index=True,
    )
    is_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class EventJournalModel(Base):
    __tablename__ = 'event_journal'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
        index=True,
    )
    trace_id: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    source: Mapped[EventSource] = mapped_column(Enum(EventSource, native_enum=False), nullable=False)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, native_enum=False), nullable=False)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus, native_enum=False), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class IngestionCursorModel(Base):
    __tablename__ = 'ingestion_cursors'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False, unique=True, index=True)
    cursor_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class RuntimeScopeGuardModel(Base):
    __tablename__ = 'runtime_scope_guards'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, unique=True, index=True)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
        index=True,
    )
    mode: Mapped[RuntimeMode] = mapped_column(
        Enum(RuntimeMode, native_enum=False),
        nullable=False,
    )
    instance_id: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False)
    stale_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class GitHubEventModel(Base):
    __tablename__ = 'github_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_event_id: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False, index=True)
    source_timestamp_or_seq: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
        index=True,
    )
    repository: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    entity_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False, index=True)
    ingress_event_type: Mapped[str] = mapped_column(String(MAX_EVENT_TYPE_LENGTH), nullable=False, index=True)
    ordering_decision: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    stale_reason: Mapped[str | None] = mapped_column(String(MAX_STALE_REASON_LENGTH), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class IngressEntityCursorModel(Base):
    __tablename__ = 'ingress_entity_cursors'
    __table_args__ = (
        UniqueConstraint(
            'environment',
            'entity_key',
            name='uq_ingress_entity_cursors_environment_entity_key',
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
        index=True,
    )
    entity_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    high_water_source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    high_water_source_event_id: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class OutboxEntryModel(Base):
    __tablename__ = 'outbox_entries'
    __table_args__ = (
        UniqueConstraint(
            'environment',
            'action_type',
            'target_identity',
            'idempotency_key',
            name='uq_outbox_environment_action_target_idempotency',
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    outbox_id: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False, unique=True, index=True)
    job_id: Mapped[str] = mapped_column(
        String(MAX_ID_LENGTH),
        ForeignKey('jobs.job_id'),
        nullable=False,
        index=True,
    )
    entity_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
        index=True,
    )
    action_type: Mapped[OutboxActionType] = mapped_column(
        Enum(OutboxActionType, native_enum=False),
        nullable=False,
        index=True,
    )
    target_identity: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(MAX_ID_LENGTH), nullable=False, index=True)
    job_lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, native_enum=False),
        nullable=False,
        default=OutboxStatus.PENDING,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


class WatcherStateModel(Base):
    __tablename__ = 'watcher_states'
    __table_args__ = (
        UniqueConstraint(
            'environment',
            'job_id',
            name='uq_watcher_states_environment_job_id',
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment: Mapped[EnvironmentName] = mapped_column(
        Enum(EnvironmentName, native_enum=False),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(MAX_ID_LENGTH),
        ForeignKey('jobs.job_id'),
        nullable=False,
        index=True,
    )
    entity_key: Mapped[str] = mapped_column(String(MAX_ENTITY_KEY_LENGTH), nullable=False, index=True)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    idle_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watch_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    checkpoint_cursor: Mapped[str | None] = mapped_column(String(MAX_ID_LENGTH), nullable=True)
    status: Mapped[WatcherStatus] = mapped_column(
        Enum(WatcherStatus, native_enum=False),
        nullable=False,
        default=WatcherStatus.ACTIVE,
        index=True,
    )
    reclaim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reclaimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)


__all__ = [
    'EntityModel',
    'EventJournalModel',
    'GitHubEventModel',
    'IngestionCursorModel',
    'IngressEntityCursorModel',
    'JobModel',
    'JobTransitionModel',
    'OutboxEntryModel',
    'RuntimeScopeGuardModel',
    'WatcherStateModel',
]
