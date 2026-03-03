from __future__ import annotations

from agent1.adapters.github.scanner import GitHubNotificationScanner
from agent1.adapters.github.scanner import GitHubIngressScanner
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobRecord
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_contracts import IngressOrderingDecision
from agent1.core.ingress_contracts import NormalizedIngressEvent
from agent1.core.ingress_normalizer import GitHubIngressNormalizer
from agent1.core.orchestrator import JobOrchestrator
from agent1.core.services.codex_executor import CodexExecutor
from agent1.core.services.ingress_cursor_store import PersistenceIngressCursorStore
from agent1.core.services.mention_action_executor import MentionActionExecutor
from agent1.core.services.telemetry_runtime import get_tracer

GITHUB_NOTIFICATION_CURSOR_KEY = 'github_notifications'


def create_runtime_ingress_coordinator(
    mention_response_template: str = '',
    clarification_template: str = '',
    reviewer_follow_up_template: str = '',
    author_follow_up_template: str = '',
    require_review_thread_reply: bool = True,
    allow_top_level_pr_fallback: bool = False,
    codex_executor: CodexExecutor | None = None,
    runtime_mode: RuntimeMode = RuntimeMode.ACTIVE,
    environment: EnvironmentName = EnvironmentName.DEV,
    orchestrator: JobOrchestrator | None = None,
    normalizer: GitHubIngressNormalizer | None = None,
) -> 'GitHubIngressCoordinator':

    '''
    Create runtime ingress coordinator with durable cursor-backed scanner wiring.

    Args:
    mention_response_template (str): Mention response template for deterministic reply comments.
    clarification_template (str): Clarification request template for insufficient-context assignments.
    reviewer_follow_up_template (str): Reviewer follow-up template for PR reviewer workflows.
    author_follow_up_template (str): Author follow-up template for PR author workflows.
    require_review_thread_reply (bool): Whether PR review-thread replies are mandatory for thread events.
    allow_top_level_pr_fallback (bool): Whether top-level PR fallback is allowed for review thread events.
    codex_executor (CodexExecutor | None): Optional Codex executor for remediation tasks.
    runtime_mode (RuntimeMode): Runtime mode used for created jobs.
    environment (EnvironmentName): Runtime environment used for ingress ordering persistence.
    orchestrator (JobOrchestrator | None): Optional orchestrator dependency override.
    normalizer (GitHubIngressNormalizer | None): Optional normalizer dependency override.

    Returns:
    GitHubIngressCoordinator: Runtime coordinator with persistent scanner cursor storage.
    '''

    scanner = GitHubNotificationScanner(
        cursor_store=PersistenceIngressCursorStore(),
        cursor_key=GITHUB_NOTIFICATION_CURSOR_KEY,
    )
    mention_executor = (
        MentionActionExecutor(
            response_template=mention_response_template,
            clarification_template=clarification_template,
            reviewer_follow_up_template=reviewer_follow_up_template,
            author_follow_up_template=author_follow_up_template,
            require_review_thread_reply=require_review_thread_reply,
            allow_top_level_pr_fallback=allow_top_level_pr_fallback,
            codex_executor=codex_executor,
        )
        if mention_response_template.strip() != ''
        else None
    )
    return GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=normalizer,
        mention_executor=mention_executor,
        runtime_mode=runtime_mode,
        environment=environment,
    )


def _create_job_record(
    normalized_event: NormalizedIngressEvent,
    runtime_mode: RuntimeMode,
) -> JobRecord:

    '''
    Create durable job contract from normalized ingress event payload.

    Args:
    normalized_event (NormalizedIngressEvent): Normalized ingress payload.

    Returns:
    JobRecord: Durable job contract for orchestrator create path.
    '''

    return JobRecord(
        job_id=normalized_event.job_id,
        entity_key=normalized_event.entity_key,
        kind=normalized_event.job_kind,
        state=normalized_event.initial_state,
        idempotency_key=normalized_event.idempotency_key,
        lease_epoch=0,
        environment=normalized_event.environment,
        mode=runtime_mode,
    )


class GitHubIngressCoordinator:
    def __init__(
        self,
        scanner: GitHubIngressScanner,
        orchestrator: JobOrchestrator | None = None,
        normalizer: GitHubIngressNormalizer | None = None,
        mention_executor: MentionActionExecutor | None = None,
        runtime_mode: RuntimeMode = RuntimeMode.ACTIVE,
        environment: EnvironmentName = EnvironmentName.DEV,
    ) -> None:
        self._scanner = scanner
        self._orchestrator = orchestrator or JobOrchestrator()
        self._normalizer = normalizer or GitHubIngressNormalizer()
        self._mention_executor = mention_executor
        self._runtime_mode = runtime_mode
        self._environment = environment

    def _process_normalized_event(self, normalized_event: NormalizedIngressEvent) -> JobRecord:
        current_job = self._orchestrator.get_job(normalized_event.job_id)
        if current_job is None:
            current_job = self._orchestrator.create_job(
                _create_job_record(
                    normalized_event=normalized_event,
                    runtime_mode=self._runtime_mode,
                ),
                trace_id=normalized_event.trace_id,
            )

        if normalized_event.should_claim_lease:
            claimed = self._orchestrator.claim_job(current_job.job_id, trace_id=normalized_event.trace_id)
            if claimed is False:
                latest_job = self._orchestrator.get_job(current_job.job_id)
                if latest_job is not None:
                    return latest_job

                return current_job

            latest_job = self._orchestrator.get_job(current_job.job_id)
            if latest_job is None:
                message = f'Job missing after successful claim: {current_job.job_id}'
                raise ValueError(message)

            current_job = latest_job

        if (
            normalized_event.transition_to is not None
            and current_job.state != normalized_event.transition_to
        ):
            try:
                current_job = self._orchestrator.transition_job(
                    current_job.job_id,
                    to_state=normalized_event.transition_to,
                    reason=normalized_event.transition_reason or 'ingress_transition',
                    trace_id=normalized_event.trace_id,
                )
            except ValueError:
                latest_job = self._orchestrator.get_job(current_job.job_id)
                if latest_job is None:
                    message = f'Job missing after transition error: {current_job.job_id}'
                    raise ValueError(message)

                current_job = latest_job

        if self._mention_executor is not None:
            return self._mention_executor.execute_for_event(
                normalized_event=normalized_event,
                current_job=current_job,
                orchestrator=self._orchestrator,
            )

        return current_job

    def process_once(self) -> list[JobRecord]:

        '''
        Create one ingress processing cycle from scan through orchestration.

        Returns:
        list[JobRecord]: Jobs touched during processing cycle.
        '''

        with get_tracer().start_as_current_span('ingress.coordinator.process_once') as span:
            ingress_events = self._scanner.scan()
            normalized_events: list[NormalizedIngressEvent] = []
            stale_events_count = 0
            for ingress_event in ingress_events:
                persisted_ingress_event = self._orchestrator.persist_ingress_event(
                    ingress_event=ingress_event,
                    environment=self._environment,
                )
                if persisted_ingress_event.ordering_decision == IngressOrderingDecision.STALE:
                    stale_events_count = stale_events_count + 1
                    continue

                normalized_event = self._normalizer.normalize_event(ingress_event)
                if normalized_event is not None:
                    normalized_events.append(normalized_event)

            span.set_attribute('agent1.ingress.events_count', len(ingress_events))
            span.set_attribute('agent1.ingress.normalized_events_count', len(normalized_events))
            span.set_attribute('agent1.ingress.stale_events_count', stale_events_count)
            processed_jobs = [self._process_normalized_event(event) for event in normalized_events]
            span.set_attribute('agent1.ingress.jobs_touched_count', len(processed_jobs))
            return processed_jobs

    def get_scanner(self) -> GitHubIngressScanner:

        '''
        Create scanner dependency access for runtime diagnostics and wiring checks.

        Returns:
        GitHubIngressScanner: Scanner dependency used by coordinator instance.
        '''

        return self._scanner


__all__ = [
    'GITHUB_NOTIFICATION_CURSOR_KEY',
    'GitHubIngressCoordinator',
    'create_runtime_ingress_coordinator',
]
