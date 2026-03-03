from __future__ import annotations

from typing import Protocol

from agent1.adapters.github.client import GitHubApiClient
from agent1.adapters.github.client import UrlLibGitHubApiClient
from agent1.core.contracts import CommentTargetType
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import NormalizedIngressEvent
from agent1.core.orchestrator import JobOrchestrator
from agent1.core.services.comment_router import CommentRouter
from agent1.core.services.comment_router import CommentRoutingError
from agent1.core.services.telemetry_runtime import get_tracer

MENTION_EXECUTION_START_REASON = 'mention_action_started'
MENTION_RESPONSE_POSTED_REASON = 'mention_response_posted'
MENTION_RESPONSE_FAILED_REASON = 'mention_response_failed'
COMMENT_ROUTE_FAILED_REASON = 'comment_route_failed'
CLARIFICATION_REQUEST_POSTED_REASON = 'clarification_request_posted'
CLARIFICATION_REQUEST_FAILED_REASON = 'clarification_request_failed'
REVIEWER_EXECUTION_START_REASON = 'reviewer_action_started'
REVIEWER_RESPONSE_POSTED_REASON = 'reviewer_response_posted'
REVIEWER_RESPONSE_FAILED_REASON = 'reviewer_response_failed'
AUTHOR_EXECUTION_START_REASON = 'author_action_started'
AUTHOR_FEEDBACK_POSTED_REASON = 'author_feedback_posted'
AUTHOR_CI_TRIAGE_POSTED_REASON = 'author_ci_triage_posted'
AUTHOR_RESPONSE_FAILED_REASON = 'author_response_failed'
AUTHOR_CODEX_EXECUTION_FAILED_REASON = 'author_codex_execution_failed'
AUTHOR_CODEX_EXECUTION_BLOCKED_REASON = 'author_codex_execution_blocked'
NO_WRITE_CLARIFICATION_REASON = 'no_write_clarification_observed'
NO_WRITE_EXECUTION_START_REASON = 'no_write_execution_started'
NO_WRITE_FEEDBACK_REASON = 'no_write_feedback_observed'
NO_WRITE_CI_REASON = 'no_write_ci_observed'


def _is_supported_comment_event(normalized_event: NormalizedIngressEvent) -> bool:
    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    return ingress_event_type in {
        IngressEventType.ISSUE_MENTION.value,
        IngressEventType.ISSUE_UPDATED.value,
        IngressEventType.PR_MENTION.value,
        IngressEventType.PR_REVIEW_COMMENT.value,
    }


def _is_clarification_event(normalized_event: NormalizedIngressEvent) -> bool:
    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    has_sufficient_context = bool(normalized_event.details.get('has_sufficient_context', True))
    return (
        ingress_event_type == IngressEventType.ISSUE_ASSIGNMENT.value
        and has_sufficient_context is False
    )


def _is_reviewer_event(normalized_event: NormalizedIngressEvent, current_job: JobRecord) -> bool:
    if current_job.kind != JobKind.PR_REVIEWER:
        return False

    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    if ingress_event_type == IngressEventType.PR_REVIEW_REQUESTED.value:
        return True
    if ingress_event_type == IngressEventType.PR_UPDATED.value:
        return bool(normalized_event.details.get('requires_follow_up', False))

    return False


def _is_author_feedback_event(normalized_event: NormalizedIngressEvent, current_job: JobRecord) -> bool:
    if current_job.kind != JobKind.PR_AUTHOR:
        return False

    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    if ingress_event_type == IngressEventType.PR_REVIEW_COMMENT.value:
        return True
    if ingress_event_type == IngressEventType.PR_UPDATED.value:
        return bool(normalized_event.details.get('requires_follow_up', False))

    return False


def _is_author_ci_event(normalized_event: NormalizedIngressEvent, current_job: JobRecord) -> bool:
    if current_job.kind != JobKind.PR_AUTHOR:
        return False

    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    return ingress_event_type == IngressEventType.PR_CI_FAILED.value


class CodexTaskExecutor(Protocol):
    def execute_task(
        self,
        task_id: str,
        prompt: str,
    ) -> ExecutionResult:
        ...


class MentionActionExecutor:
    def __init__(
        self,
        response_template: str,
        clarification_template: str,
        reviewer_follow_up_template: str,
        author_follow_up_template: str,
        require_review_thread_reply: bool = True,
        allow_top_level_pr_fallback: bool = False,
        github_client: GitHubApiClient | None = None,
        codex_executor: CodexTaskExecutor | None = None,
    ) -> None:
        self._response_template = response_template
        self._clarification_template = clarification_template
        self._reviewer_follow_up_template = reviewer_follow_up_template
        self._author_follow_up_template = author_follow_up_template
        self._comment_router = CommentRouter(
            require_review_thread_reply=require_review_thread_reply,
            allow_top_level_pr_fallback=allow_top_level_pr_fallback,
        )
        self._github_client = github_client or UrlLibGitHubApiClient()
        self._codex_executor = codex_executor

    def _render_comment_body(self, normalized_event: NormalizedIngressEvent) -> str:
        try:
            return self._response_template.format(
                repository=normalized_event.repository,
                entity_number=normalized_event.entity_number,
                entity_key=normalized_event.entity_key,
            )
        except KeyError:
            return self._response_template

    def _render_clarification_body(self, normalized_event: NormalizedIngressEvent) -> str:
        try:
            return self._clarification_template.format(
                repository=normalized_event.repository,
                entity_number=normalized_event.entity_number,
                entity_key=normalized_event.entity_key,
            )
        except KeyError:
            return self._clarification_template

    def _render_reviewer_follow_up_body(self, normalized_event: NormalizedIngressEvent) -> str:
        try:
            return self._reviewer_follow_up_template.format(
                repository=normalized_event.repository,
                entity_number=normalized_event.entity_number,
                entity_key=normalized_event.entity_key,
            )
        except KeyError:
            return self._reviewer_follow_up_template

    def _render_author_follow_up_body(self, normalized_event: NormalizedIngressEvent) -> str:
        try:
            return self._author_follow_up_template.format(
                repository=normalized_event.repository,
                entity_number=normalized_event.entity_number,
                entity_key=normalized_event.entity_key,
                check_name=normalized_event.details.get('check_name', ''),
                conclusion=normalized_event.details.get('conclusion', ''),
            )
        except KeyError:
            return self._author_follow_up_template

    def _build_author_codex_prompt(self, normalized_event: NormalizedIngressEvent) -> str:
        ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
        check_name = str(normalized_event.details.get('check_name', ''))
        conclusion = str(normalized_event.details.get('conclusion', ''))
        return '\n'.join(
            [
                f"Repository: {normalized_event.repository}",
                f"Entity: {normalized_event.entity_key}",
                f"IngressEvent: {ingress_event_type}",
                f"CheckName: {check_name}",
                f"Conclusion: {conclusion}",
                'Task: Apply deterministic PR author follow-up implementation changes.',
            ]
        )

    def _execute_author_codex_task(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
    ) -> ExecutionStatus | None:
        if self._codex_executor is None:
            return None

        task_id = f"{current_job.job_id}:{normalized_event.event_id}:author_follow_up"
        try:
            execution_result = self._codex_executor.execute_task(
                task_id=task_id,
                prompt=self._build_author_codex_prompt(normalized_event),
            )
        except Exception:
            return ExecutionStatus.FAILED

        return execution_result.status

    def _validate_mutating_lease(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        orchestrator: JobOrchestrator,
    ) -> tuple[JobRecord, bool]:
        lease_valid = orchestrator.validate_mutating_lease(
            job_id=current_job.job_id,
            expected_lease_epoch=current_job.lease_epoch,
            trace_id=normalized_event.trace_id,
        )
        latest_job = orchestrator.get_job(current_job.job_id)
        if latest_job is None:
            return current_job, lease_valid

        return latest_job, lease_valid

    def _execute_no_write_event(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        orchestrator: JobOrchestrator,
    ) -> JobRecord:
        if current_job.state == JobState.AWAITING_CONTEXT and _is_clarification_event(normalized_event):
            return orchestrator.transition_job(
                current_job.job_id,
                to_state=JobState.BLOCKED,
                reason=NO_WRITE_CLARIFICATION_REASON,
                trace_id=normalized_event.trace_id,
            )

        if current_job.state != JobState.READY_TO_EXECUTE:
            return current_job

        handles_feedback = (
            _is_reviewer_event(normalized_event, current_job)
            or _is_author_feedback_event(normalized_event, current_job)
            or _is_supported_comment_event(normalized_event)
        )
        handles_ci = _is_author_ci_event(normalized_event, current_job)
        if handles_feedback is False and handles_ci is False:
            return current_job

        target_state = JobState.AWAITING_HUMAN_FEEDBACK
        target_reason = NO_WRITE_FEEDBACK_REASON
        if handles_ci:
            target_state = JobState.AWAITING_CI
            target_reason = NO_WRITE_CI_REASON

        no_write_executing_job = orchestrator.transition_job(
            current_job.job_id,
            to_state=JobState.EXECUTING,
            reason=NO_WRITE_EXECUTION_START_REASON,
            trace_id=normalized_event.trace_id,
        )
        return orchestrator.transition_job(
            no_write_executing_job.job_id,
            to_state=target_state,
            reason=target_reason,
            trace_id=normalized_event.trace_id,
        )

    def execute_for_event(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        orchestrator: JobOrchestrator,
    ) -> JobRecord:

        '''
        Create deterministic mention side-effect flow for eligible ready-to-execute jobs.

        Args:
        normalized_event (NormalizedIngressEvent): Normalized ingress event payload.
        current_job (JobRecord): Current durable job state.
        orchestrator (JobOrchestrator): Job orchestrator for deterministic transitions.

        Returns:
        JobRecord: Updated durable job state after mention side-effect handling.
        '''

        with get_tracer().start_as_current_span('ingress.mention_action.execute') as span:
            span.set_attribute('agent1.entity_key', normalized_event.entity_key)
            span.set_attribute('agent1.job_id', current_job.job_id)
            span.set_attribute('agent1.event_id', normalized_event.event_id)
            if current_job.mode != RuntimeMode.ACTIVE:
                return self._execute_no_write_event(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )

            if current_job.state == JobState.AWAITING_CONTEXT and _is_clarification_event(normalized_event):
                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                clarification_body = self._render_clarification_body(normalized_event)
                try:
                    self._github_client.post_issue_comment(
                        repository=normalized_event.repository,
                        issue_number=normalized_event.entity_number,
                        body=clarification_body,
                    )
                except Exception:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=CLARIFICATION_REQUEST_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                    )

                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=CLARIFICATION_REQUEST_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )

            if current_job.state != JobState.READY_TO_EXECUTE:
                return current_job
            if _is_reviewer_event(normalized_event, current_job):
                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                reviewer_body = self._render_reviewer_follow_up_body(normalized_event)
                try:
                    self._github_client.post_issue_comment(
                        repository=normalized_event.repository,
                        issue_number=normalized_event.entity_number,
                        body=reviewer_body,
                    )
                except Exception:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=REVIEWER_RESPONSE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                    )

                reviewer_executing_job = orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.EXECUTING,
                    reason=REVIEWER_EXECUTION_START_REASON,
                    trace_id=normalized_event.trace_id,
                )
                return orchestrator.transition_job(
                    reviewer_executing_job.job_id,
                    to_state=JobState.AWAITING_HUMAN_FEEDBACK,
                    reason=REVIEWER_RESPONSE_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )
            if _is_author_feedback_event(normalized_event, current_job):
                author_codex_status = self._execute_author_codex_task(normalized_event, current_job)
                if author_codex_status == ExecutionStatus.FAILED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                    )
                if author_codex_status == ExecutionStatus.BLOCKED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_BLOCKED_REASON,
                        trace_id=normalized_event.trace_id,
                    )

                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                author_comment_body = self._render_author_follow_up_body(normalized_event)
                try:
                    comment_target = self._comment_router.route(normalized_event)
                except CommentRoutingError as error:
                    orchestrator.emit_comment_routing_failure_alert(
                        environment=current_job.environment,
                        trace_id=normalized_event.trace_id,
                        job_id=current_job.job_id,
                        entity_key=current_job.entity_key,
                        error_message=str(error),
                    )
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=COMMENT_ROUTE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                    )

                try:
                    if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
                        if comment_target.review_comment_id is None:
                            raise ValueError('Missing review comment id for thread reply.')
                        self._github_client.post_pull_review_comment_reply(
                            repository=normalized_event.repository,
                            pull_number=normalized_event.entity_number,
                            review_comment_id=comment_target.review_comment_id,
                            body=author_comment_body,
                        )
                    else:
                        self._github_client.post_issue_comment(
                            repository=normalized_event.repository,
                            issue_number=normalized_event.entity_number,
                            body=author_comment_body,
                        )
                except Exception:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_RESPONSE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                    )

                author_executing_job = orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.EXECUTING,
                    reason=AUTHOR_EXECUTION_START_REASON,
                    trace_id=normalized_event.trace_id,
                )
                return orchestrator.transition_job(
                    author_executing_job.job_id,
                    to_state=JobState.AWAITING_HUMAN_FEEDBACK,
                    reason=AUTHOR_FEEDBACK_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )
            if _is_author_ci_event(normalized_event, current_job):
                author_codex_status = self._execute_author_codex_task(normalized_event, current_job)
                if author_codex_status == ExecutionStatus.FAILED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                    )
                if author_codex_status == ExecutionStatus.BLOCKED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_BLOCKED_REASON,
                        trace_id=normalized_event.trace_id,
                    )

                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                author_ci_body = self._render_author_follow_up_body(normalized_event)
                try:
                    self._github_client.post_issue_comment(
                        repository=normalized_event.repository,
                        issue_number=normalized_event.entity_number,
                        body=author_ci_body,
                    )
                except Exception:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_RESPONSE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                    )

                author_executing_job = orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.EXECUTING,
                    reason=AUTHOR_EXECUTION_START_REASON,
                    trace_id=normalized_event.trace_id,
                )
                return orchestrator.transition_job(
                    author_executing_job.job_id,
                    to_state=JobState.AWAITING_CI,
                    reason=AUTHOR_CI_TRIAGE_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )

            if _is_supported_comment_event(normalized_event) is False:
                return current_job

            try:
                comment_target = self._comment_router.route(normalized_event)
            except CommentRoutingError as error:
                orchestrator.emit_comment_routing_failure_alert(
                    environment=current_job.environment,
                    trace_id=normalized_event.trace_id,
                    job_id=current_job.job_id,
                    entity_key=current_job.entity_key,
                    error_message=str(error),
                )
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=COMMENT_ROUTE_FAILED_REASON,
                    trace_id=normalized_event.trace_id,
                )

            current_job, lease_valid = self._validate_mutating_lease(
                normalized_event=normalized_event,
                current_job=current_job,
                orchestrator=orchestrator,
            )
            if lease_valid is False:
                return current_job

            comment_body = self._render_comment_body(normalized_event)
            try:
                if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
                    if comment_target.review_comment_id is None:
                        raise ValueError('Missing review comment id for thread reply.')
                    self._github_client.post_pull_review_comment_reply(
                        repository=normalized_event.repository,
                        pull_number=normalized_event.entity_number,
                        review_comment_id=comment_target.review_comment_id,
                        body=comment_body,
                    )
                else:
                    self._github_client.post_issue_comment(
                        repository=normalized_event.repository,
                        issue_number=normalized_event.entity_number,
                        body=comment_body,
                    )
            except Exception:
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=MENTION_RESPONSE_FAILED_REASON,
                    trace_id=normalized_event.trace_id,
                )

            executing_job = orchestrator.transition_job(
                current_job.job_id,
                to_state=JobState.EXECUTING,
                reason=MENTION_EXECUTION_START_REASON,
                trace_id=normalized_event.trace_id,
            )
            return orchestrator.transition_job(
                executing_job.job_id,
                to_state=JobState.AWAITING_HUMAN_FEEDBACK,
                reason=MENTION_RESPONSE_POSTED_REASON,
                trace_id=normalized_event.trace_id,
            )


__all__ = ['MentionActionExecutor']
