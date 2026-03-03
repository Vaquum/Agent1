from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import RuntimeMode
from agent1.db.models import RuntimeScopeGuardModel
from agent1.db.repositories.runtime_scope_guard_repository import RuntimeScopeGuardRepository
from agent1.db.session import create_session_factory

DEFAULT_SCOPE_STALE_AFTER_SECONDS = 120


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for scope guard coordination.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


def _compute_scope_key(
    active_repositories: list[str],
    require_sandbox_scope_for_dev_active: bool,
    sandbox_label: str,
    sandbox_branch_prefix: str,
) -> str:

    '''
    Compute deterministic runtime scope key from active repository and sandbox boundaries.

    Args:
    active_repositories (list[str]): Runtime active repository scope list.
    require_sandbox_scope_for_dev_active (bool): Runtime sandbox-scope enforcement flag.
    sandbox_label (str): Runtime sandbox label marker.
    sandbox_branch_prefix (str): Runtime sandbox branch prefix marker.

    Returns:
    str: Deterministic scope key used for startup ownership fencing.
    '''

    normalized_repositories = sorted(
        {
            repository.strip()
            for repository in active_repositories
            if repository.strip() != ''
        },
    )
    repositories_fragment = ','.join(normalized_repositories)
    sandbox_label_fragment = ''
    sandbox_branch_prefix_fragment = ''
    if require_sandbox_scope_for_dev_active:
        sandbox_label_fragment = sandbox_label.strip()
        sandbox_branch_prefix_fragment = sandbox_branch_prefix.strip()

    return '|'.join(
        [
            f'repositories={repositories_fragment}',
            f'sandbox_required={require_sandbox_scope_for_dev_active}',
            f'sandbox_label={sandbox_label_fragment}',
            f'sandbox_branch_prefix={sandbox_branch_prefix_fragment}',
        ],
    )


class RuntimeScopeConflictError(RuntimeError):
    pass


class RuntimeScopeGuard:
    def __init__(
        self,
        environment: EnvironmentName,
        mode: RuntimeMode,
        instance_id: str,
        active_repositories: list[str],
        require_sandbox_scope_for_dev_active: bool,
        sandbox_label: str,
        sandbox_branch_prefix: str,
        stale_after_seconds: int = DEFAULT_SCOPE_STALE_AFTER_SECONDS,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        normalized_instance_id = instance_id.strip()
        if normalized_instance_id == '':
            message = 'Runtime instance identifier must not be empty.'
            raise ValueError(message)

        self._environment = environment
        self._mode = mode
        self._instance_id = normalized_instance_id
        self._scope_key = _compute_scope_key(
            active_repositories=active_repositories,
            require_sandbox_scope_for_dev_active=require_sandbox_scope_for_dev_active,
            sandbox_label=sandbox_label,
            sandbox_branch_prefix=sandbox_branch_prefix,
        )
        self._stale_after_seconds = stale_after_seconds
        self._session_factory = session_factory or create_session_factory()

    def get_scope_key(self) -> str:

        '''
        Create deterministic runtime scope key value used for startup fencing.

        Returns:
        str: Runtime scope key.
        '''

        return self._scope_key

    def acquire_scope_guard(self) -> None:

        '''
        Create startup ownership claim for active runtime scope fencing.

        Raises:
        RuntimeScopeConflictError: Raised when an active scope owner already holds the same scope.
        '''

        if self._mode != RuntimeMode.ACTIVE:
            return

        reference_timestamp = _utc_now()
        with self._session_factory() as session:
            repository = RuntimeScopeGuardRepository(session)
            scope_guard_model = repository.get_scope_guard(self._scope_key)
            if scope_guard_model is None:
                try:
                    repository.create_scope_guard(
                        scope_key=self._scope_key,
                        environment=self._environment,
                        mode=self._mode,
                        instance_id=self._instance_id,
                        stale_after_seconds=self._stale_after_seconds,
                        acquired_at=reference_timestamp,
                        heartbeat_at=reference_timestamp,
                    )
                    session.commit()
                    return
                except IntegrityError as error:
                    session.rollback()
                    raise RuntimeScopeConflictError(
                        f'Runtime scope already claimed for key {self._scope_key}.',
                    ) from error

            if self._is_owned_by_current_instance(scope_guard_model):
                repository.update_scope_guard(
                    scope_guard_model=scope_guard_model,
                    environment=self._environment,
                    mode=self._mode,
                    instance_id=self._instance_id,
                    stale_after_seconds=self._stale_after_seconds,
                    heartbeat_at=reference_timestamp,
                )
                session.commit()
                return

            if self._is_stale(scope_guard_model, reference_timestamp):
                repository.update_scope_guard(
                    scope_guard_model=scope_guard_model,
                    environment=self._environment,
                    mode=self._mode,
                    instance_id=self._instance_id,
                    stale_after_seconds=self._stale_after_seconds,
                    heartbeat_at=reference_timestamp,
                )
                session.commit()
                return

            raise RuntimeScopeConflictError(
                'Runtime scope conflict detected for key '
                f'{self._scope_key}. Existing owner {scope_guard_model.instance_id} '
                f'in environment {scope_guard_model.environment.value}.',
            )

    def release_scope_guard(self) -> None:

        '''
        Create runtime scope guard release for current active instance ownership.
        '''

        if self._mode != RuntimeMode.ACTIVE:
            return

        with self._session_factory() as session:
            repository = RuntimeScopeGuardRepository(session)
            repository.delete_scope_guard(
                scope_key=self._scope_key,
                instance_id=self._instance_id,
            )
            session.commit()

    def _is_owned_by_current_instance(self, scope_guard_model: RuntimeScopeGuardModel) -> bool:
        return scope_guard_model.instance_id == self._instance_id

    def _is_stale(
        self,
        scope_guard_model: RuntimeScopeGuardModel,
        reference_timestamp: datetime,
    ) -> bool:
        heartbeat_timestamp = _ensure_utc_timestamp(scope_guard_model.heartbeat_at)
        heartbeat_age_seconds = (reference_timestamp - heartbeat_timestamp).total_seconds()
        return heartbeat_age_seconds > scope_guard_model.stale_after_seconds


__all__ = ['RuntimeScopeConflictError', 'RuntimeScopeGuard']
