from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import RuntimeMode
from agent1.db.models import RuntimeScopeGuardModel


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class RuntimeScopeGuardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_scope_guard(self, scope_key: str) -> RuntimeScopeGuardModel | None:

        '''
        Create runtime scope guard lookup result by deterministic scope key.

        Args:
        scope_key (str): Deterministic runtime scope key.

        Returns:
        RuntimeScopeGuardModel | None: Persisted scope guard row or None when missing.
        '''

        return (
            self._session.query(RuntimeScopeGuardModel)
            .filter(RuntimeScopeGuardModel.scope_key == scope_key)
            .one_or_none()
        )

    def create_scope_guard(
        self,
        scope_key: str,
        environment: EnvironmentName,
        mode: RuntimeMode,
        instance_id: str,
        stale_after_seconds: int,
        acquired_at: datetime,
        heartbeat_at: datetime,
    ) -> RuntimeScopeGuardModel:

        '''
        Create runtime scope guard row for active startup ownership fencing.

        Args:
        scope_key (str): Deterministic runtime scope key.
        environment (EnvironmentName): Runtime environment value.
        mode (RuntimeMode): Runtime mode value.
        instance_id (str): Runtime instance identifier.
        stale_after_seconds (int): Stale threshold for guard takeover checks.
        acquired_at (datetime): Scope guard acquisition timestamp.
        heartbeat_at (datetime): Latest guard heartbeat timestamp.

        Returns:
        RuntimeScopeGuardModel: Persisted scope guard row.
        '''

        scope_guard_model = RuntimeScopeGuardModel(
            scope_key=scope_key,
            environment=environment,
            mode=mode,
            instance_id=instance_id,
            stale_after_seconds=stale_after_seconds,
            acquired_at=_ensure_utc_timestamp(acquired_at),
            heartbeat_at=_ensure_utc_timestamp(heartbeat_at),
        )
        self._session.add(scope_guard_model)
        self._session.flush()
        return scope_guard_model

    def update_scope_guard(
        self,
        scope_guard_model: RuntimeScopeGuardModel,
        environment: EnvironmentName,
        mode: RuntimeMode,
        instance_id: str,
        stale_after_seconds: int,
        heartbeat_at: datetime,
    ) -> RuntimeScopeGuardModel:

        '''
        Create runtime scope guard heartbeat refresh or takeover update.

        Args:
        scope_guard_model (RuntimeScopeGuardModel): Persisted scope guard row to update.
        environment (EnvironmentName): Runtime environment value.
        mode (RuntimeMode): Runtime mode value.
        instance_id (str): Runtime instance identifier.
        stale_after_seconds (int): Stale threshold for guard takeover checks.
        heartbeat_at (datetime): Latest guard heartbeat timestamp.

        Returns:
        RuntimeScopeGuardModel: Updated scope guard row.
        '''

        scope_guard_model.environment = environment
        scope_guard_model.mode = mode
        scope_guard_model.instance_id = instance_id
        scope_guard_model.stale_after_seconds = stale_after_seconds
        scope_guard_model.heartbeat_at = _ensure_utc_timestamp(heartbeat_at)
        self._session.flush()
        return scope_guard_model

    def delete_scope_guard(self, scope_key: str, instance_id: str) -> bool:

        '''
        Create runtime scope guard release result for a specific owner instance.

        Args:
        scope_key (str): Deterministic runtime scope key.
        instance_id (str): Runtime instance identifier expected to own the guard.

        Returns:
        bool: True when guard row is deleted, otherwise False.
        '''

        scope_guard_model = self.get_scope_guard(scope_key)
        if scope_guard_model is None:
            return False

        if scope_guard_model.instance_id != instance_id:
            return False

        self._session.delete(scope_guard_model)
        self._session.flush()
        return True


__all__ = ['RuntimeScopeGuardRepository']
