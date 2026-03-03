from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxStatus
from agent1.core.services.idempotency_schema import IDEMPOTENCY_DEFAULT_POLICY_VERSION
from agent1.core.services.idempotency_schema import build_canonical_idempotency_scope
from agent1.db.models import OutboxEntryModel


@dataclass(frozen=True)
class IdempotencyScopeViolation:
    idempotency_key: str
    outbox_ids: list[str]
    scopes: list[str]
    entry_count: int


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for outbox persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_outbox_entry(
        self,
        outbox_id: str,
        job_id: str,
        entity_key: str,
        environment: EnvironmentName,
        action_type: OutboxActionType,
        target_identity: str,
        payload: dict[str, object],
        idempotency_key: str,
        job_lease_epoch: int,
        idempotency_policy_version: str = IDEMPOTENCY_DEFAULT_POLICY_VERSION,
        idempotency_schema_version: str | None = None,
        idempotency_payload_hash: str | None = None,
        idempotency_policy_version_hash: str | None = None,
        next_attempt_at: datetime | None = None,
    ) -> OutboxEntryModel:

        '''
        Create persisted outbox entry row for deterministic side-effect dispatch.

        Args:
        outbox_id (str): Durable outbox identifier.
        job_id (str): Durable job identifier linked to the side effect.
        entity_key (str): Entity key for routing and audit context.
        environment (EnvironmentName): Runtime environment value.
        action_type (OutboxActionType): Outbox side-effect action type.
        target_identity (str): Deterministic target identity for idempotency scope.
        payload (dict[str, object]): Outbound side-effect payload.
        idempotency_key (str): Deterministic idempotency key.
        job_lease_epoch (int): Job lease epoch captured at side-effect intent creation.
        idempotency_policy_version (str): Policy version used for idempotency schema composition.
        idempotency_schema_version (str | None): Optional idempotency schema version override.
        idempotency_payload_hash (str | None): Optional payload hash override.
        idempotency_policy_version_hash (str | None): Optional policy-version hash override.
        next_attempt_at (datetime | None): Optional first-attempt schedule timestamp.

        Returns:
        OutboxEntryModel: Persisted outbox entry model.
        '''

        normalized_next_attempt_at = None
        if next_attempt_at is not None:
            normalized_next_attempt_at = _ensure_utc_timestamp(next_attempt_at)

        canonical_scope = build_canonical_idempotency_scope(
            entity_key=entity_key,
            action_type=action_type,
            target_identity=target_identity,
            payload=payload,
            policy_version=idempotency_policy_version,
        )
        should_enforce_schema = (
            idempotency_schema_version is not None
            or idempotency_payload_hash is not None
            or idempotency_policy_version_hash is not None
        )
        resolved_schema_version = idempotency_schema_version
        resolved_payload_hash = idempotency_payload_hash
        resolved_policy_version_hash = idempotency_policy_version_hash
        if should_enforce_schema:
            if idempotency_key != canonical_scope.idempotency_key:
                raise ValueError('Idempotency key does not match canonical schema scope.')
            if (
                idempotency_schema_version is not None
                and idempotency_schema_version != canonical_scope.schema_version
            ):
                raise ValueError('Idempotency schema version does not match canonical schema scope.')
            if (
                idempotency_payload_hash is not None
                and idempotency_payload_hash != canonical_scope.payload_hash
            ):
                raise ValueError('Idempotency payload hash does not match canonical schema scope.')
            if (
                idempotency_policy_version_hash is not None
                and idempotency_policy_version_hash != canonical_scope.policy_version_hash
            ):
                raise ValueError('Idempotency policy version hash does not match canonical schema scope.')
            resolved_schema_version = canonical_scope.schema_version
            resolved_payload_hash = canonical_scope.payload_hash
            resolved_policy_version_hash = canonical_scope.policy_version_hash

        model = OutboxEntryModel(
            outbox_id=outbox_id,
            job_id=job_id,
            entity_key=entity_key,
            environment=environment,
            action_type=action_type,
            target_identity=target_identity,
            payload=payload,
            idempotency_key=idempotency_key,
            idempotency_schema_version=resolved_schema_version,
            idempotency_payload_hash=resolved_payload_hash,
            idempotency_policy_version_hash=resolved_policy_version_hash,
            job_lease_epoch=job_lease_epoch,
            status=OutboxStatus.PENDING,
            next_attempt_at=normalized_next_attempt_at,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def get_outbox_entry_by_outbox_id(self, outbox_id: str) -> OutboxEntryModel | None:

        '''
        Create outbox entry lookup result by durable outbox identifier.

        Args:
        outbox_id (str): Durable outbox identifier.

        Returns:
        OutboxEntryModel | None: Matching outbox entry model or None when missing.
        '''

        return self._session.query(OutboxEntryModel).filter(OutboxEntryModel.outbox_id == outbox_id).one_or_none()

    def get_outbox_entry_by_idempotency_scope(
        self,
        environment: EnvironmentName,
        action_type: OutboxActionType,
        target_identity: str,
        idempotency_key: str,
        idempotency_schema_version: str | None = None,
        idempotency_payload_hash: str | None = None,
        idempotency_policy_version_hash: str | None = None,
    ) -> OutboxEntryModel | None:

        '''
        Create outbox entry lookup result by deterministic idempotency scope.

        Args:
        environment (EnvironmentName): Runtime environment value.
        action_type (OutboxActionType): Outbox side-effect action type.
        target_identity (str): Deterministic target identity.
        idempotency_key (str): Deterministic idempotency key.
        idempotency_schema_version (str | None): Optional idempotency schema version filter.
        idempotency_payload_hash (str | None): Optional payload hash filter.
        idempotency_policy_version_hash (str | None): Optional policy-version hash filter.

        Returns:
        OutboxEntryModel | None: Matching outbox entry model or None when missing.
        '''

        query = (
            self._session.query(OutboxEntryModel)
            .filter(OutboxEntryModel.environment == environment)
            .filter(OutboxEntryModel.action_type == action_type)
            .filter(OutboxEntryModel.target_identity == target_identity)
            .filter(OutboxEntryModel.idempotency_key == idempotency_key)
        )
        if idempotency_schema_version is not None:
            query = query.filter(OutboxEntryModel.idempotency_schema_version == idempotency_schema_version)
        if idempotency_payload_hash is not None:
            query = query.filter(OutboxEntryModel.idempotency_payload_hash == idempotency_payload_hash)
        if idempotency_policy_version_hash is not None:
            query = query.filter(
                OutboxEntryModel.idempotency_policy_version_hash == idempotency_policy_version_hash,
            )

        return query.one_or_none()

    def list_dispatchable_entries(
        self,
        limit: int,
        reference_timestamp: datetime | None = None,
    ) -> list[OutboxEntryModel]:

        '''
        Create dispatchable outbox entry list for retry-safe dispatcher cycles.

        Args:
        limit (int): Maximum number of entries to return.
        reference_timestamp (datetime | None): Optional dispatch reference timestamp.

        Returns:
        list[OutboxEntryModel]: Ordered dispatchable outbox entries.
        '''

        dispatch_reference = _utc_now() if reference_timestamp is None else _ensure_utc_timestamp(
            reference_timestamp,
        )
        return (
            self._session.query(OutboxEntryModel)
            .filter(
                OutboxEntryModel.status.in_(
                    [
                        OutboxStatus.PENDING,
                        OutboxStatus.FAILED,
                        OutboxStatus.SENT,
                    ],
                ),
            )
            .filter(
                (OutboxEntryModel.next_attempt_at.is_(None))
                | (OutboxEntryModel.next_attempt_at <= dispatch_reference),
            )
            .order_by(OutboxEntryModel.created_at.asc())
            .limit(limit)
            .all()
        )

    def mark_entry_sent(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        attempt_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute sent-status update outcome for one outbox entry attempt.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        attempt_timestamp (datetime | None): Optional attempt timestamp override.

        Returns:
        bool: True when update succeeded, otherwise False.
        '''

        model = self.get_outbox_entry_by_outbox_id(outbox_id)
        if model is None:
            return False

        if model.lease_epoch != expected_lease_epoch:
            return False

        normalized_attempt_timestamp = _utc_now()
        if attempt_timestamp is not None:
            normalized_attempt_timestamp = _ensure_utc_timestamp(attempt_timestamp)

        model.status = OutboxStatus.SENT
        model.attempt_count = model.attempt_count + 1
        model.lease_epoch = model.lease_epoch + 1
        model.last_attempt_at = normalized_attempt_timestamp
        model.next_attempt_at = normalized_attempt_timestamp
        model.last_error = None
        model.updated_at = normalized_attempt_timestamp
        self._session.flush()
        return True

    def mark_entry_confirmed(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        confirmation_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute confirmed-status update outcome for one outbox entry.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        confirmation_timestamp (datetime | None): Optional confirmation timestamp override.

        Returns:
        bool: True when update succeeded, otherwise False.
        '''

        model = self.get_outbox_entry_by_outbox_id(outbox_id)
        if model is None:
            return False

        if model.lease_epoch != expected_lease_epoch:
            return False

        normalized_confirmation_timestamp = _utc_now()
        if confirmation_timestamp is not None:
            normalized_confirmation_timestamp = _ensure_utc_timestamp(confirmation_timestamp)

        model.status = OutboxStatus.CONFIRMED
        model.lease_epoch = model.lease_epoch + 1
        model.next_attempt_at = None
        model.last_error = None
        model.updated_at = normalized_confirmation_timestamp
        self._session.flush()
        return True

    def mark_entry_failed(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        error_message: str,
        retry_after_seconds: int,
        failure_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute failed-status update outcome and retry schedule for one entry.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        error_message (str): Deterministic failure summary.
        retry_after_seconds (int): Retry delay in seconds.
        failure_timestamp (datetime | None): Optional failure timestamp override.

        Returns:
        bool: True when update succeeded, otherwise False.
        '''

        model = self.get_outbox_entry_by_outbox_id(outbox_id)
        if model is None:
            return False

        if model.lease_epoch != expected_lease_epoch:
            return False

        normalized_failure_timestamp = _utc_now()
        if failure_timestamp is not None:
            normalized_failure_timestamp = _ensure_utc_timestamp(failure_timestamp)

        model.status = OutboxStatus.FAILED
        model.lease_epoch = model.lease_epoch + 1
        model.last_error = error_message
        model.next_attempt_at = normalized_failure_timestamp + timedelta(seconds=retry_after_seconds)
        model.updated_at = normalized_failure_timestamp
        self._session.flush()
        return True

    def mark_entry_aborted(
        self,
        outbox_id: str,
        expected_lease_epoch: int,
        abort_reason: str,
        abort_timestamp: datetime | None = None,
    ) -> bool:

        '''
        Compute aborted-status update outcome for unrecoverable outbox entries.

        Args:
        outbox_id (str): Durable outbox identifier.
        expected_lease_epoch (int): Expected lease epoch fencing value.
        abort_reason (str): Deterministic abort summary.
        abort_timestamp (datetime | None): Optional abort timestamp override.

        Returns:
        bool: True when update succeeded, otherwise False.
        '''

        model = self.get_outbox_entry_by_outbox_id(outbox_id)
        if model is None:
            return False

        if model.lease_epoch != expected_lease_epoch:
            return False

        normalized_abort_timestamp = _utc_now()
        if abort_timestamp is not None:
            normalized_abort_timestamp = _ensure_utc_timestamp(abort_timestamp)

        model.status = OutboxStatus.ABORTED
        model.lease_epoch = model.lease_epoch + 1
        model.next_attempt_at = None
        model.last_error = abort_reason
        model.updated_at = normalized_abort_timestamp
        self._session.flush()
        return True

    def count_backlog_entries(self) -> int:

        '''
        Create backlog row count across dispatchable outbox statuses.

        Returns:
        int: Outbox row count in pending, sent, or failed states.
        '''

        return (
            self._session.query(OutboxEntryModel)
            .filter(
                OutboxEntryModel.status.in_(
                    [
                        OutboxStatus.PENDING,
                        OutboxStatus.SENT,
                        OutboxStatus.FAILED,
                    ],
                ),
            )
            .count()
        )

    def list_idempotency_scope_violations(
        self,
        environment: EnvironmentName,
        limit: int = 50,
    ) -> list[IdempotencyScopeViolation]:

        '''
        Create idempotency-scope violation list for one environment.

        Args:
        environment (EnvironmentName): Runtime environment value.
        limit (int): Maximum number of violations to return.

        Returns:
        list[IdempotencyScopeViolation]: Deterministic idempotency-scope violations.
        '''

        models = (
            self._session.query(OutboxEntryModel)
            .filter(OutboxEntryModel.environment == environment)
            .order_by(OutboxEntryModel.created_at.asc(), OutboxEntryModel.id.asc())
            .all()
        )
        grouped_models: dict[str, list[OutboxEntryModel]] = {}
        for model in models:
            grouped_models.setdefault(model.idempotency_key, []).append(model)

        violations: list[IdempotencyScopeViolation] = []
        for idempotency_key in sorted(grouped_models.keys()):
            scoped_models = grouped_models[idempotency_key]
            if len(scoped_models) <= 1:
                continue

            scope_set: set[str] = set()
            for scoped_model in scoped_models:
                scope_value = '|'.join(
                    [
                        scoped_model.action_type.value,
                        scoped_model.target_identity,
                        scoped_model.idempotency_schema_version or '',
                        scoped_model.idempotency_payload_hash or '',
                        scoped_model.idempotency_policy_version_hash or '',
                    ],
                )
                scope_set.add(scope_value)

            if len(scope_set) <= 1:
                continue

            violations.append(
                IdempotencyScopeViolation(
                    idempotency_key=idempotency_key,
                    outbox_ids=sorted({scoped_model.outbox_id for scoped_model in scoped_models}),
                    scopes=sorted(scope_set),
                    entry_count=len(scoped_models),
                ),
            )
            if len(violations) >= limit:
                break

        return violations


__all__ = ['IdempotencyScopeViolation', 'OutboxRepository']
