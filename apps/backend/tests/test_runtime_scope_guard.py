from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import RuntimeMode
from agent1.core.services.runtime_scope_guard import RuntimeScopeConflictError
from agent1.core.services.runtime_scope_guard import RuntimeScopeGuard
from agent1.db.repositories.runtime_scope_guard_repository import RuntimeScopeGuardRepository


def _create_scope_guard(
    session_factory: sessionmaker[Session],
    instance_id: str,
    mode: RuntimeMode = RuntimeMode.ACTIVE,
) -> RuntimeScopeGuard:
    return RuntimeScopeGuard(
        environment=EnvironmentName.DEV,
        mode=mode,
        instance_id=instance_id,
        active_repositories=['Vaquum/Agent1'],
        require_sandbox_scope_for_dev_active=True,
        sandbox_label='agent1-sandbox',
        sandbox_branch_prefix='sandbox/',
        session_factory=session_factory,
    )


def test_runtime_scope_guard_rejects_overlapping_active_scope(
    session_factory: sessionmaker[Session],
) -> None:
    first_scope_guard = _create_scope_guard(
        session_factory=session_factory,
        instance_id='instance-a',
    )
    second_scope_guard = _create_scope_guard(
        session_factory=session_factory,
        instance_id='instance-b',
    )

    first_scope_guard.acquire_scope_guard()
    with pytest.raises(RuntimeScopeConflictError):
        second_scope_guard.acquire_scope_guard()

    first_scope_guard.release_scope_guard()
    second_scope_guard.acquire_scope_guard()

    with session_factory() as session:
        repository = RuntimeScopeGuardRepository(session)
        scope_guard_model = repository.get_scope_guard(second_scope_guard.get_scope_key())
        assert scope_guard_model is not None
        assert scope_guard_model.instance_id == 'instance-b'


def test_runtime_scope_guard_skips_non_active_modes(
    session_factory: sessionmaker[Session],
) -> None:
    shadow_scope_guard = _create_scope_guard(
        session_factory=session_factory,
        instance_id='instance-shadow',
        mode=RuntimeMode.SHADOW,
    )
    shadow_scope_guard.acquire_scope_guard()

    with session_factory() as session:
        repository = RuntimeScopeGuardRepository(session)
        assert repository.get_scope_guard(shadow_scope_guard.get_scope_key()) is None
