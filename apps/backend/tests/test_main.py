from __future__ import annotations

from agent1.adapters.github.scanner import GitHubNotificationScanner
from agent1.core.ingress_coordinator import GitHubIngressCoordinator
from agent1.core.services.codex_executor import CodexExecutor
from agent1.core.services.ingress_worker import IngressWorker
from agent1.core.services.runtime_scope_guard import RuntimeScopeGuard
from agent1.core.services.trace_context import TRACE_HEADER_NAME
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
    assert isinstance(application.state.codex_executor, CodexExecutor)
    assert isinstance(application.state.sentry_enabled, bool)
    assert isinstance(application.state.otel_enabled, bool)
    assert application.state.trace_header_name == TRACE_HEADER_NAME
    route_paths = {
        path
        for path in (getattr(route, 'path', None) for route in application.routes)
        if isinstance(path, str)
    }
    assert '/dashboard/overview' in route_paths
    assert '/dashboard/jobs/{job_id}/timeline' in route_paths
