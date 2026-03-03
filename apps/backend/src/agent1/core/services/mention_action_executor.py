from __future__ import annotations

from datetime import datetime
from datetime import timezone
import hashlib
from typing import Protocol

from agent1.adapters.github.client import GitHubApiClient
from agent1.adapters.github.client import UrlLibGitHubApiClient
from agent1.core.contracts import CommentTarget
from agent1.core.contracts import CommentTargetRecord
from agent1.core.contracts import CommentTargetType
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxRecord
from agent1.core.contracts import OutboxStatus
from agent1.core.contracts import OutboxWriteRequest
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import NormalizedIngressEvent
from agent1.core.orchestrator import JobOrchestrator
from agent1.core.services.comment_router import CommentRouter
from agent1.core.services.comment_router import CommentRoutingError
from agent1.core.services.idempotency_schema import IDEMPOTENCY_DEFAULT_POLICY_VERSION
from agent1.core.services.idempotency_schema import build_canonical_idempotency_scope
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
COMMENT_TARGET_OUTBOX_ABORT_REASON = 'comment_target_delivery_failed'


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_supported_comment_event(normalized_event: NormalizedIngressEvent) -> bool:
    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    if ingress_event_type == IngressEventType.ISSUE_ASSIGNMENT.value:
        return bool(normalized_event.details.get('has_sufficient_context', True))

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
        idempotency_policy_version: str = IDEMPOTENCY_DEFAULT_POLICY_VERSION,
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
        self._idempotency_policy_version = idempotency_policy_version
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

    def _create_comment_target_identity(
        self,
        normalized_event: NormalizedIngressEvent,
        comment_target: CommentTarget,
    ) -> str:
        if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
            thread_id = str(comment_target.thread_id or '')
            review_comment_id = int(comment_target.review_comment_id or 0)
            return (
                f"{normalized_event.repository}:"
                f"pr:{normalized_event.entity_number}:"
                f"thread:{thread_id}:{review_comment_id}"
            )

        if comment_target.target_type == CommentTargetType.PR:
            return f"{normalized_event.repository}:pr:{normalized_event.entity_number}"

        return f"{normalized_event.repository}:issue:{normalized_event.entity_number}"

    def _create_comment_target_outbox_id(
        self,
        normalized_event: NormalizedIngressEvent,
        action_type: OutboxActionType,
        target_identity: str,
    ) -> str:
        target_hash = hashlib.sha1(target_identity.encode('utf-8')).hexdigest()[:12]
        return f"outbox_route:{normalized_event.event_id}:{action_type.value}:{target_hash}"

    def _build_comment_target_record(
        self,
        outbox_id: str,
        current_job: JobRecord,
        comment_target: CommentTarget,
        target_identity: str,
    ) -> CommentTargetRecord:
        return CommentTargetRecord(
            target_id=outbox_id,
            outbox_id=outbox_id,
            job_id=current_job.job_id,
            entity_key=current_job.entity_key,
            environment=current_job.environment,
            target_type=comment_target.target_type,
            target_identity=target_identity,
            issue_number=comment_target.issue_number,
            pr_number=comment_target.pr_number,
            thread_id=comment_target.thread_id,
            review_comment_id=comment_target.review_comment_id,
            path=comment_target.path,
            line=comment_target.line,
            side=comment_target.side,
            resolved_at=_utc_now(),
        )

    def _build_comment_target_intent(
        self,
        normalized_event: NormalizedIngressEvent,
        comment_target: CommentTarget,
        comment_body: str,
    ) -> tuple[OutboxActionType, str, dict[str, object]]:
        target_identity = self._create_comment_target_identity(normalized_event, comment_target)

        if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
            if comment_target.review_comment_id is None:
                raise ValueError('Missing review comment id for thread reply.')

            return (
                OutboxActionType.PR_REVIEW_REPLY,
                target_identity,
                {
                    'repository': normalized_event.repository,
                    'pull_number': normalized_event.entity_number,
                    'review_comment_id': comment_target.review_comment_id,
                    'body': comment_body,
                },
            )

        return (
            OutboxActionType.ISSUE_COMMENT,
            target_identity,
            {
                'repository': normalized_event.repository,
                'issue_number': normalized_event.entity_number,
                'body': comment_body,
            },
        )

    def _persist_comment_target_intent(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        comment_target: CommentTarget,
        comment_body: str,
        orchestrator: JobOrchestrator,
    ) -> tuple[OutboxRecord, OutboxActionType]:
        action_type, target_identity, payload = self._build_comment_target_intent(
            normalized_event=normalized_event,
            comment_target=comment_target,
            comment_body=comment_body,
        )
        idempotency_scope = build_canonical_idempotency_scope(
            entity_key=current_job.entity_key,
            action_type=action_type,
            target_identity=target_identity,
            payload=payload,
            policy_version=self._idempotency_policy_version,
        )
        idempotency_key = idempotency_scope.idempotency_key
        existing_outbox = orchestrator.get_outbox_entry_by_idempotency_scope(
            environment=current_job.environment,
            action_type=action_type,
            target_identity=target_identity,
            idempotency_key=idempotency_key,
            idempotency_schema_version=idempotency_scope.schema_version,
            idempotency_payload_hash=idempotency_scope.payload_hash,
            idempotency_policy_version_hash=idempotency_scope.policy_version_hash,
        )
        if existing_outbox is not None:
            existing_comment_target = orchestrator.get_comment_target_by_outbox_id(
                environment=current_job.environment,
                outbox_id=existing_outbox.outbox_id,
            )
            if existing_comment_target is None:
                orchestrator.append_comment_target(
                    self._build_comment_target_record(
                        outbox_id=existing_outbox.outbox_id,
                        current_job=current_job,
                        comment_target=comment_target,
                        target_identity=target_identity,
                    ),
                )
            return existing_outbox, action_type

        outbox_id = self._create_comment_target_outbox_id(
            normalized_event=normalized_event,
            action_type=action_type,
            target_identity=target_identity,
        )
        existing_outbox_by_outbox_id = orchestrator.get_outbox_entry_by_outbox_id(outbox_id)
        if existing_outbox_by_outbox_id is not None:
            existing_comment_target = orchestrator.get_comment_target_by_outbox_id(
                environment=current_job.environment,
                outbox_id=existing_outbox_by_outbox_id.outbox_id,
            )
            if existing_comment_target is None:
                orchestrator.append_comment_target(
                    self._build_comment_target_record(
                        outbox_id=existing_outbox_by_outbox_id.outbox_id,
                        current_job=current_job,
                        comment_target=comment_target,
                        target_identity=target_identity,
                    ),
                )
            return existing_outbox_by_outbox_id, action_type

        outbox_record = orchestrator.append_outbox_entry(
            OutboxWriteRequest(
                outbox_id=outbox_id,
                job_id=current_job.job_id,
                entity_key=current_job.entity_key,
                environment=current_job.environment,
                action_type=action_type,
                target_identity=target_identity,
                payload=payload,
                idempotency_key=idempotency_key,
                idempotency_policy_version=self._idempotency_policy_version,
                idempotency_schema_version=idempotency_scope.schema_version,
                idempotency_payload_hash=idempotency_scope.payload_hash,
                idempotency_policy_version_hash=idempotency_scope.policy_version_hash,
                job_lease_epoch=current_job.lease_epoch,
            ),
        )
        orchestrator.append_comment_target(
            self._build_comment_target_record(
                outbox_id=outbox_record.outbox_id,
                current_job=current_job,
                comment_target=comment_target,
                target_identity=target_identity,
            ),
        )
        return outbox_record, action_type

    def _dispatch_comment_target(
        self,
        normalized_event: NormalizedIngressEvent,
        comment_target: CommentTarget,
        comment_body: str,
    ) -> None:
        if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
            if comment_target.review_comment_id is None:
                raise ValueError('Missing review comment id for thread reply.')

            self._github_client.post_pull_review_comment_reply(
                repository=normalized_event.repository,
                pull_number=normalized_event.entity_number,
                review_comment_id=comment_target.review_comment_id,
                body=comment_body,
            )
            return

        self._github_client.post_issue_comment(
            repository=normalized_event.repository,
            issue_number=normalized_event.entity_number,
            body=comment_body,
        )

    def _deliver_comment_target(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        comment_target: CommentTarget,
        comment_body: str,
        orchestrator: JobOrchestrator,
    ) -> bool:
        outbox_record, _ = self._persist_comment_target_intent(
            normalized_event=normalized_event,
            current_job=current_job,
            comment_target=comment_target,
            comment_body=comment_body,
            orchestrator=orchestrator,
        )
        if outbox_record.status == OutboxStatus.CONFIRMED:
            return True

        sent = orchestrator.mark_outbox_entry_sent(
            outbox_id=outbox_record.outbox_id,
            expected_lease_epoch=outbox_record.lease_epoch,
        )
        if sent is False:
            return False

        sent_lease_epoch = outbox_record.lease_epoch + 1
        try:
            self._dispatch_comment_target(
                normalized_event=normalized_event,
                comment_target=comment_target,
                comment_body=comment_body,
            )
        except Exception:
            orchestrator.mark_outbox_entry_aborted(
                outbox_id=outbox_record.outbox_id,
                expected_lease_epoch=sent_lease_epoch,
                abort_reason=COMMENT_TARGET_OUTBOX_ABORT_REASON,
            )
            return False

        return orchestrator.mark_outbox_entry_confirmed(
            outbox_id=outbox_record.outbox_id,
            expected_lease_epoch=sent_lease_epoch,
        )

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

                delivered = self._deliver_comment_target(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    comment_target=comment_target,
                    comment_body=author_comment_body,
                    orchestrator=orchestrator,
                )
                if delivered is False:
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
            delivered = self._deliver_comment_target(
                normalized_event=normalized_event,
                current_job=current_job,
                comment_target=comment_target,
                comment_body=comment_body,
                orchestrator=orchestrator,
            )
            if delivered is False:
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
