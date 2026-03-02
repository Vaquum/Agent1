from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi import Response
from fastapi import FastAPI
from starlette.middleware.base import RequestResponseEndpoint

from agent1.api.dashboard import router as dashboard_router
from agent1.api.health import router as health_router
from agent1.config.settings import get_settings
from agent1.core.contracts import EnvironmentName
from agent1.core.control_loader import validate_control_bundle
from agent1.core.ingress_coordinator import create_runtime_ingress_coordinator
from agent1.core.ingress_normalizer import GitHubIngressNormalizer
from agent1.core.services.codex_executor import CodexExecutor
from agent1.core.services.ingress_worker import IngressWorker
from agent1.core.services.runtime_scope_guard import RuntimeScopeGuard
from agent1.core.services.sentry_runtime import initialize_sentry
from agent1.core.services.telemetry_runtime import initialize_telemetry
from agent1.core.services.trace_context import TRACE_HEADER_NAME
from agent1.core.services.trace_context import get_or_create_trace_id
from agent1.core.services.trace_context import reset_trace_id
from agent1.core.services.trace_context import set_trace_id

APP_NAME = 'Agent1 Backend'
APP_VERSION = '0.1.0'


def _register_trace_middleware(application: FastAPI) -> None:

    '''
    Create request middleware binding trace identifiers to runtime context.

    Args:
    application (FastAPI): FastAPI application instance.
    '''

    @application.middleware('http')
    async def _trace_context_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_id = get_or_create_trace_id(request.headers.get(TRACE_HEADER_NAME))
        token = set_trace_id(trace_id)
        try:
            response = await call_next(request)
            response.headers[TRACE_HEADER_NAME] = trace_id
            return response
        finally:
            reset_trace_id(token)


def _create_lifespan(
    ingress_worker: IngressWorker,
    runtime_scope_guard: RuntimeScopeGuard,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:

    '''
    Create FastAPI lifespan handler that manages ingress worker lifecycle.

    Args:
    ingress_worker (IngressWorker): Runtime ingress worker instance.
    runtime_scope_guard (RuntimeScopeGuard): Runtime startup scope guard instance.

    Returns:
    Callable[[FastAPI], AbstractAsyncContextManager[None]]: Lifespan context manager callable.
    '''

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        runtime_scope_guard.acquire_scope_guard()
        try:
            ingress_worker.start_background()
            try:
                yield
            finally:
                ingress_worker.request_stop()
                ingress_worker.join()
        finally:
            runtime_scope_guard.release_scope_guard()

    return _lifespan


def create_application() -> FastAPI:

    '''
    Create FastAPI application instance for Agent1 runtime.

    Returns:
    FastAPI: Configured FastAPI application.
    '''

    control_bundle = validate_control_bundle()
    settings = get_settings()
    sentry_enabled = initialize_sentry()
    codex_executor = CodexExecutor()
    mention_response_template = control_bundle.prompts.templates['mention_response'].task_prompt
    clarification_template = control_bundle.prompts.templates['issue_clarification'].task_prompt
    reviewer_follow_up_template = control_bundle.prompts.templates['reviewer_follow_up'].task_prompt
    author_follow_up_template = control_bundle.prompts.templates['pr_follow_up'].task_prompt
    ingress_normalizer = GitHubIngressNormalizer(
        runtime_mode=control_bundle.runtime.mode,
        active_repositories=control_bundle.runtime.active_repositories,
        require_sandbox_scope_for_dev_active=(
            control_bundle.runtime.require_sandbox_scope_for_dev_active
        ),
        sandbox_label=control_bundle.runtime.sandbox_label,
        sandbox_branch_prefix=control_bundle.runtime.sandbox_branch_prefix,
        agent_actor=control_bundle.policies.agent_actor,
        ignored_actors=control_bundle.policies.ignored_actors,
        ignored_actor_suffixes=control_bundle.policies.ignored_actor_suffixes,
    )
    ingress_coordinator = create_runtime_ingress_coordinator(
        mention_response_template=mention_response_template,
        clarification_template=clarification_template,
        reviewer_follow_up_template=reviewer_follow_up_template,
        author_follow_up_template=author_follow_up_template,
        require_review_thread_reply=control_bundle.commenting.require_review_thread_reply,
        allow_top_level_pr_fallback=control_bundle.commenting.allow_top_level_pr_fallback,
        codex_executor=codex_executor,
        runtime_mode=control_bundle.runtime.mode,
        normalizer=ingress_normalizer,
    )
    ingress_worker = IngressWorker(
        ingress_processor=ingress_coordinator,
        poll_interval_seconds=control_bundle.runtime.poll_interval_seconds,
    )
    runtime_scope_guard = RuntimeScopeGuard(
        environment=EnvironmentName.DEV,
        mode=control_bundle.runtime.mode,
        instance_id=settings.runtime_instance_id,
        active_repositories=control_bundle.runtime.active_repositories,
        require_sandbox_scope_for_dev_active=(
            control_bundle.runtime.require_sandbox_scope_for_dev_active
        ),
        sandbox_label=control_bundle.runtime.sandbox_label,
        sandbox_branch_prefix=control_bundle.runtime.sandbox_branch_prefix,
    )
    application = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        lifespan=_create_lifespan(
            ingress_worker=ingress_worker,
            runtime_scope_guard=runtime_scope_guard,
        ),
    )
    otel_enabled = initialize_telemetry(application)
    _register_trace_middleware(application)
    application.state.control_bundle = control_bundle
    application.state.sentry_enabled = sentry_enabled
    application.state.otel_enabled = otel_enabled
    application.state.trace_header_name = TRACE_HEADER_NAME
    application.state.ingress_coordinator = ingress_coordinator
    application.state.ingress_worker = ingress_worker
    application.state.runtime_scope_guard = runtime_scope_guard
    application.state.codex_executor = codex_executor
    application.include_router(dashboard_router)
    application.include_router(health_router)
    return application


app = create_application()

__all__ = ['app', 'create_application']
