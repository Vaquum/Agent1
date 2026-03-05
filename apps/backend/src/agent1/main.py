from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Request
from fastapi import Response
from fastapi import FastAPI
from starlette.middleware.base import RequestResponseEndpoint

from agent1.api.dashboard import router as dashboard_router
from agent1.api.health import router as health_router
from agent1.config.settings import get_settings
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.control_loader import get_project_root
from agent1.core.control_loader import validate_control_bundle
from agent1.core.ingress_coordinator import create_runtime_ingress_coordinator
from agent1.core.ingress_normalizer import GitHubIngressNormalizer
from agent1.core.services.alert_signal_service import AlertSignalService
from agent1.core.services.codex_executor import CodexExecutor
from agent1.core.services.ingress_worker import IngressWorker
from agent1.core.services.release_promotion_gate_service import ReleasePromotionGateService
from agent1.core.services.rollout_guard_service import RolloutGuardService
from agent1.core.services.rollout_stage_gate import RolloutStageGateEvaluator
from agent1.core.services.runtime_controls_service import RuntimeControlsService
from agent1.core.services.runtime_scope_guard import RuntimeScopeGuard
from agent1.core.services.sentry_runtime import initialize_sentry
from agent1.core.services.stop_the_line_service import StopTheLineService
from agent1.core.services.telemetry_runtime import initialize_telemetry
from agent1.core.services.trace_context import TRACE_HEADER_NAME
from agent1.core.services.trace_context import get_or_create_trace_id
from agent1.core.services.trace_context import reset_trace_id
from agent1.core.services.trace_context import set_trace_id
from agent1.core.services.watcher_lifecycle_service import WatcherLifecycleService

APP_NAME = 'Agent1 Backend'
APP_VERSION = '0.1.0'
RUNTIME_CONTROLS_STATE_FILE_NAME = 'runtime-controls-state.json'


def _resolve_runtime_controls_state_path() -> Path:

    '''
    Create runtime controls state path with persistent volume preference.

    Returns:
    Path: Runtime controls state file path.
    '''

    volume_runtime_controls_root = Path('/data')
    if volume_runtime_controls_root.exists() and volume_runtime_controls_root.is_dir():
        return volume_runtime_controls_root / RUNTIME_CONTROLS_STATE_FILE_NAME

    return get_project_root() / f'.agent1-{RUNTIME_CONTROLS_STATE_FILE_NAME}'


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


def _resolve_runtime_environment(runtime_environment_value: str) -> EnvironmentName:

    '''
    Create runtime environment enum from settings configuration value.

    Args:
    runtime_environment_value (str): Runtime environment configuration string.

    Returns:
    EnvironmentName: Parsed runtime environment value.
    '''

    normalized_runtime_environment_value = runtime_environment_value.strip().lower()
    try:
        return EnvironmentName(normalized_runtime_environment_value)
    except ValueError as error:
        message = (
            'Unsupported runtime environment setting value: '
            f'{runtime_environment_value}'
        )
        raise ValueError(message) from error


def _resolve_runtime_mode(
    control_mode: RuntimeMode,
    runtime_mode_override_value: str,
) -> RuntimeMode:

    '''
    Create runtime mode from control default and optional settings override.

    Args:
    control_mode (RuntimeMode): Runtime mode defined by active control bundle.
    runtime_mode_override_value (str): Runtime mode override from settings.

    Returns:
    RuntimeMode: Effective runtime mode.
    '''

    normalized_runtime_mode_override_value = runtime_mode_override_value.strip().lower()
    if normalized_runtime_mode_override_value == '':
        return control_mode

    try:
        return RuntimeMode(normalized_runtime_mode_override_value)
    except ValueError as error:
        message = (
            'Unsupported runtime mode override setting value: '
            f'{runtime_mode_override_value}'
        )
        raise ValueError(message) from error


def _resolve_runtime_github_user(github_user_value: str) -> str:

    '''
    Create normalized runtime GitHub user identity from settings configuration.

    Args:
    github_user_value (str): GitHub user configuration string.

    Returns:
    str: Normalized GitHub user identity.
    '''

    return github_user_value.strip()


def create_application() -> FastAPI:

    '''
    Create FastAPI application instance for Agent1 runtime.

    Returns:
    FastAPI: Configured FastAPI application.
    '''

    control_bundle = validate_control_bundle()
    settings = get_settings()
    runtime_github_user = _resolve_runtime_github_user(settings.github_user)
    if runtime_github_user != '':
        control_bundle.policies.agent_actor = runtime_github_user
        control_bundle.policies.mutating_credential_owner_by_environment.dev = runtime_github_user
        control_bundle.policies.mutating_credential_owner_by_environment.prod = runtime_github_user
        control_bundle.policies.mutating_credential_owner_by_environment.ci = runtime_github_user
    runtime_controls_service = RuntimeControlsService(
        default_active_repositories=control_bundle.runtime.active_repositories,
        state_path=_resolve_runtime_controls_state_path(),
    )
    runtime_active_repositories = runtime_controls_service.get_active_repositories()
    control_bundle.runtime.active_repositories = runtime_active_repositories
    runtime_environment = _resolve_runtime_environment(settings.runtime_environment)
    runtime_mode = _resolve_runtime_mode(
        control_mode=control_bundle.runtime.mode,
        runtime_mode_override_value=settings.runtime_mode_override,
    )
    sentry_enabled = initialize_sentry()
    codex_executor = CodexExecutor(
        policies=control_bundle.policies,
        runtime_environment=runtime_environment,
    )
    rollout_stage_gate_evaluator = RolloutStageGateEvaluator(
        rollout_policy=control_bundle.runtime.rollout_policy,
    )
    rollout_guard_service = RolloutGuardService(
        stage_gate_evaluator=rollout_stage_gate_evaluator,
    )
    release_promotion_gate_service = ReleasePromotionGateService(
        release_promotion_policy=control_bundle.runtime.release_promotion_policy,
    )
    stop_the_line_service = StopTheLineService(
        stop_the_line_policy=control_bundle.runtime.stop_the_line_policy,
    )
    mention_response_template = control_bundle.prompts.templates['mention_response'].task_prompt
    clarification_template = control_bundle.prompts.templates['issue_clarification'].task_prompt
    reviewer_follow_up_template = control_bundle.prompts.templates['reviewer_follow_up'].task_prompt
    issue_mention_codex_prompt_template = control_bundle.prompts.templates[
        'issue_mention_codex'
    ].task_prompt
    pr_mention_codex_prompt_template = control_bundle.prompts.templates[
        'pr_mention_codex'
    ].task_prompt
    issue_assignment_codex_prompt_template = control_bundle.prompts.templates[
        'issue_assignment_codex'
    ].task_prompt
    reviewer_codex_review_prompt_template = control_bundle.prompts.templates[
        'reviewer_codex_review'
    ].task_prompt
    reviewer_codex_thread_reply_prompt_template = control_bundle.prompts.templates[
        'reviewer_codex_thread_reply'
    ].task_prompt
    author_follow_up_template = control_bundle.prompts.templates['pr_follow_up'].task_prompt
    author_codex_prompt_template = control_bundle.prompts.templates['author_codex_follow_up'].task_prompt
    ingress_normalizer = GitHubIngressNormalizer(
        environment=runtime_environment,
        runtime_mode=runtime_mode,
        active_repositories=runtime_active_repositories,
        require_sandbox_scope_for_dev_active=(
            control_bundle.runtime.require_sandbox_scope_for_dev_active
        ),
        sandbox_label=control_bundle.runtime.sandbox_label,
        sandbox_branch_prefix=control_bundle.runtime.sandbox_branch_prefix,
        agent_actor=runtime_github_user,
        ignored_actors=control_bundle.policies.ignored_actors,
        ignored_actor_suffixes=control_bundle.policies.ignored_actor_suffixes,
    )
    ingress_coordinator = create_runtime_ingress_coordinator(
        mention_response_template=mention_response_template,
        clarification_template=clarification_template,
        reviewer_follow_up_template=reviewer_follow_up_template,
        issue_mention_codex_prompt_template=issue_mention_codex_prompt_template,
        pr_mention_codex_prompt_template=pr_mention_codex_prompt_template,
        issue_assignment_codex_prompt_template=issue_assignment_codex_prompt_template,
        reviewer_codex_review_prompt_template=reviewer_codex_review_prompt_template,
        reviewer_codex_thread_reply_prompt_template=reviewer_codex_thread_reply_prompt_template,
        author_follow_up_template=author_follow_up_template,
        author_codex_prompt_template=author_codex_prompt_template,
        require_review_thread_reply=control_bundle.commenting.require_review_thread_reply,
        allow_top_level_pr_fallback=control_bundle.commenting.allow_top_level_pr_fallback,
        idempotency_policy_version=control_bundle.policies.version,
        codex_executor=codex_executor,
        runtime_mode=runtime_mode,
        environment=runtime_environment,
        normalizer=ingress_normalizer,
    )
    alert_signal_service = AlertSignalService()
    watcher_lifecycle_service = WatcherLifecycleService(
        environment=runtime_environment,
        watch_interval_seconds=control_bundle.runtime.watch_interval_seconds,
        stale_after_seconds=max(control_bundle.runtime.watch_interval_seconds * 2, 30),
        max_reclaim_attempts=max(control_bundle.runtime.max_retry_attempts, 1),
        watch_deadline_seconds=max(control_bundle.runtime.watch_interval_seconds * 20, 300),
        terminal_states_by_job_kind={
            JobKind(job_rule.job_kind): {JobState(state) for state in job_rule.terminal_states}
            for job_rule in control_bundle.jobs.rules
        },
    )
    ingress_worker = IngressWorker(
        ingress_processor=ingress_coordinator,
        poll_interval_seconds=control_bundle.runtime.poll_interval_seconds,
        environment=runtime_environment,
        runtime_mode=runtime_mode,
        watcher_lifecycle_service=watcher_lifecycle_service,
        alert_signal_service=alert_signal_service,
        stop_the_line_service=stop_the_line_service,
    )
    runtime_scope_guard = RuntimeScopeGuard(
        environment=runtime_environment,
        mode=runtime_mode,
        instance_id=settings.runtime_instance_id,
        active_repositories=runtime_active_repositories,
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
    application.state.runtime_environment = runtime_environment
    application.state.runtime_mode = runtime_mode
    application.state.codex_executor = codex_executor
    application.state.rollout_stage_gate_evaluator = rollout_stage_gate_evaluator
    application.state.rollout_guard_service = rollout_guard_service
    application.state.release_promotion_gate_service = release_promotion_gate_service
    application.state.stop_the_line_service = stop_the_line_service
    application.state.alert_signal_service = alert_signal_service
    application.state.watcher_lifecycle_service = watcher_lifecycle_service
    application.state.runtime_controls_service = runtime_controls_service
    application.include_router(dashboard_router)
    application.include_router(health_router)
    return application


app = create_application()

__all__ = ['app', 'create_application']
