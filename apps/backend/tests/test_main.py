from __future__ import annotations

import pytest

from agent1.adapters.github.scanner import GitHubNotificationScanner
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_coordinator import GitHubIngressCoordinator
from agent1.core.services.codex_executor import CodexExecutor
from agent1.core.services.ingress_worker import IngressWorker
from agent1.core.services.release_promotion_gate_service import ReleasePromotionGateService
from agent1.core.services.rollout_guard_service import RolloutGuardService
from agent1.core.services.rollout_stage_gate import RolloutStageGateEvaluator
from agent1.core.services.runtime_scope_guard import RuntimeScopeGuard
from agent1.core.services.stop_the_line_service import StopTheLineService
from agent1.core.services.trace_context import TRACE_HEADER_NAME
from agent1.main import _resolve_runtime_environment
from agent1.main import _resolve_runtime_mode
from agent1.main import create_application


def test_create_application_sets_runtime_ingress_coordinator() -> None:
    application = create_application()
    coordinator = application.state.ingress_coordinator
    scanner = coordinator.get_scanner()

    assert isinstance(coordinator, GitHubIngressCoordinator)
    assert isinstance(scanner, GitHubNotificationScanner)
    assert scanner.get_cursor_store() is not None
    assert isinstance(application.state.ingress_worker, IngressWorker)
    assert application.state.ingress_worker.is_running() is False
    assert isinstance(application.state.runtime_scope_guard, RuntimeScopeGuard)
    assert isinstance(application.state.runtime_environment, EnvironmentName)
    assert isinstance(application.state.runtime_mode, RuntimeMode)
    assert isinstance(application.state.codex_executor, CodexExecutor)
    assert isinstance(application.state.rollout_stage_gate_evaluator, RolloutStageGateEvaluator)
    assert isinstance(application.state.rollout_guard_service, RolloutGuardService)
    assert isinstance(application.state.release_promotion_gate_service, ReleasePromotionGateService)
    assert isinstance(application.state.stop_the_line_service, StopTheLineService)
    assert isinstance(application.state.sentry_enabled, bool)
    assert isinstance(application.state.otel_enabled, bool)
    assert application.state.trace_header_name == TRACE_HEADER_NAME
    route_paths = {
        path
        for path in (getattr(route, 'path', None) for route in application.routes)
        if isinstance(path, str)
    }
    assert '/dashboard/overview' in route_paths
    assert '/dashboard/controls/active-repositories' in route_paths
    assert '/dashboard/jobs/{job_id}/timeline' in route_paths
    assert '/dashboard/alerts/stop-the-line/acknowledge' in route_paths


def test_resolve_runtime_environment_parses_supported_value() -> None:
    resolved_environment = _resolve_runtime_environment('prod')
    assert resolved_environment == EnvironmentName.PROD


def test_resolve_runtime_environment_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match='Unsupported runtime environment setting value'):
        _resolve_runtime_environment('unknown')


def test_resolve_runtime_mode_uses_control_value_when_override_is_empty() -> None:
    resolved_mode = _resolve_runtime_mode(
        control_mode=RuntimeMode.ACTIVE,
        runtime_mode_override_value='',
    )
    assert resolved_mode == RuntimeMode.ACTIVE


def test_resolve_runtime_mode_parses_supported_override_value() -> None:
    resolved_mode = _resolve_runtime_mode(
        control_mode=RuntimeMode.ACTIVE,
        runtime_mode_override_value='shadow',
    )
    assert resolved_mode == RuntimeMode.SHADOW


def test_resolve_runtime_mode_rejects_invalid_override_value() -> None:
    with pytest.raises(ValueError, match='Unsupported runtime mode override setting value'):
        _resolve_runtime_mode(
            control_mode=RuntimeMode.ACTIVE,
            runtime_mode_override_value='unknown',
        )
