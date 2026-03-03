from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from agent1.adapters.github.client import GitHubApiClient
from agent1.adapters.github.client import UrlLibGitHubApiClient
from agent1.core.contracts import ActionAttemptRecord
from agent1.core.contracts import ActionAttemptStatus
from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxRecord
from agent1.core.contracts import OutboxStatus
from agent1.core.services.alert_signal_service import AlertSignalService
from agent1.core.services.persistence_service import PersistenceService

DEFAULT_DISPATCH_BATCH_SIZE = 20
DEFAULT_RETRY_AFTER_SECONDS = 30
DISPATCHER_RECONCILIATION_ABORT_REASON = 'outbox_reconciliation_detected_confirmed_duplicate'
DISPATCHER_LEASE_VALIDATION_ABORT_REASON = 'lease_epoch_validation_failed'
DISPATCHER_CONFIRMATION_ABORT_REASON = 'outbox_confirmation_failed'


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OutboxDispatcher:
    def __init__(
        self,
        persistence_service: PersistenceService | None = None,
        github_client: GitHubApiClient | None = None,
        alert_signal_service: AlertSignalService | None = None,
        dispatch_batch_size: int = DEFAULT_DISPATCH_BATCH_SIZE,
        retry_after_seconds: int = DEFAULT_RETRY_AFTER_SECONDS,
    ) -> None:
        self._persistence_service = persistence_service or PersistenceService()
        self._github_client = github_client or UrlLibGitHubApiClient()
        self._alert_signal_service = alert_signal_service or AlertSignalService(self._persistence_service)
        self._dispatch_batch_size = dispatch_batch_size
        self._retry_after_seconds = retry_after_seconds

    def dispatch_once(self) -> int:

        '''
        Compute one deterministic outbox dispatch cycle result count.

        Returns:
        int: Count of confirmed outbox entries in this cycle.
        '''

        dispatchable_entries = self._persistence_service.list_dispatchable_outbox_entries(
            limit=self._dispatch_batch_size,
        )
        if len(dispatchable_entries) > 0:
            self._alert_signal_service.maybe_emit_outbox_backlog_growth(
                environment=dispatchable_entries[0].environment,
                trace_id=f"trc_{dispatchable_entries[0].outbox_id}",
            )
        confirmed_count = 0
        for outbox_entry in dispatchable_entries:
            if self._reconcile_before_retry(outbox_entry):
                continue

            if self._validate_mutating_lease(outbox_entry) is False:
                continue

            sent = self._persistence_service.mark_outbox_entry_sent(
                outbox_id=outbox_entry.outbox_id,
                expected_lease_epoch=outbox_entry.lease_epoch,
            )
            if sent is False:
                continue

            sent_lease_epoch = outbox_entry.lease_epoch + 1
            attempt_id = self._create_attempt_id(outbox_entry)
            attempt_started_at = _utc_now()
            self._persistence_service.append_action_attempt(
                ActionAttemptRecord(
                    attempt_id=attempt_id,
                    outbox_id=outbox_entry.outbox_id,
                    job_id=outbox_entry.job_id,
                    entity_key=outbox_entry.entity_key,
                    environment=outbox_entry.environment,
                    action_type=outbox_entry.action_type,
                    status=ActionAttemptStatus.STARTED,
                    error_message=None,
                    attempt_started_at=attempt_started_at,
                    attempt_completed_at=None,
                ),
            )
            try:
                self._dispatch_outbox_entry(outbox_entry)
            except Exception as error:
                self._persistence_service.mark_outbox_entry_failed(
                    outbox_id=outbox_entry.outbox_id,
                    expected_lease_epoch=sent_lease_epoch,
                    error_message=str(error),
                    retry_after_seconds=self._retry_after_seconds,
                )
                self._persistence_service.mark_action_attempt_status(
                    environment=outbox_entry.environment,
                    attempt_id=attempt_id,
                    status=ActionAttemptStatus.FAILED,
                    completion_timestamp=_utc_now(),
                    error_message=str(error),
                )
                continue

            confirmed = self._persistence_service.mark_outbox_entry_confirmed(
                outbox_id=outbox_entry.outbox_id,
                expected_lease_epoch=sent_lease_epoch,
            )
            if confirmed:
                self._persistence_service.mark_action_attempt_status(
                    environment=outbox_entry.environment,
                    attempt_id=attempt_id,
                    status=ActionAttemptStatus.SUCCEEDED,
                    completion_timestamp=_utc_now(),
                    error_message=None,
                )
                confirmed_count = confirmed_count + 1
                continue

            self._persistence_service.mark_action_attempt_status(
                environment=outbox_entry.environment,
                attempt_id=attempt_id,
                status=ActionAttemptStatus.ABORTED,
                completion_timestamp=_utc_now(),
                error_message=DISPATCHER_CONFIRMATION_ABORT_REASON,
            )

        return confirmed_count

    def _create_attempt_id(self, outbox_entry: OutboxRecord) -> str:

        '''
        Create deterministic attempt identifier for one outbox dispatch attempt.

        Args:
        outbox_entry (OutboxRecord): Outbox entry candidate for dispatch.

        Returns:
        str: Deterministic attempt identifier.
        '''

        return f"{outbox_entry.outbox_id}:{outbox_entry.attempt_count + 1}"

    def _reconcile_before_retry(self, outbox_entry: OutboxRecord) -> bool:

        '''
        Compute reconciliation result by idempotency scope before retry dispatch.

        Args:
        outbox_entry (OutboxRecord): Outbox entry candidate for dispatch.

        Returns:
        bool: True when reconciliation handled entry without dispatch attempt.
        '''

        if outbox_entry.status == OutboxStatus.PENDING:
            return False

        scope_entry = self._persistence_service.get_outbox_entry_by_idempotency_scope(
            environment=outbox_entry.environment,
            action_type=outbox_entry.action_type,
            target_identity=outbox_entry.target_identity,
            idempotency_key=outbox_entry.idempotency_key,
        )
        if scope_entry is None:
            return False

        if scope_entry.status != OutboxStatus.CONFIRMED:
            return False

        if scope_entry.outbox_id == outbox_entry.outbox_id:
            return False

        self._persistence_service.mark_outbox_entry_aborted(
            outbox_id=outbox_entry.outbox_id,
            expected_lease_epoch=outbox_entry.lease_epoch,
            abort_reason=DISPATCHER_RECONCILIATION_ABORT_REASON,
        )
        now = _utc_now()
        self._persistence_service.append_action_attempt(
            ActionAttemptRecord(
                attempt_id=self._create_attempt_id(outbox_entry),
                outbox_id=outbox_entry.outbox_id,
                job_id=outbox_entry.job_id,
                entity_key=outbox_entry.entity_key,
                environment=outbox_entry.environment,
                action_type=outbox_entry.action_type,
                status=ActionAttemptStatus.ABORTED,
                error_message=DISPATCHER_RECONCILIATION_ABORT_REASON,
                attempt_started_at=now,
                attempt_completed_at=now,
            ),
        )
        self._alert_signal_service.emit_duplicate_side_effect_anomaly(
            environment=outbox_entry.environment,
            trace_id=f"trc_{outbox_entry.outbox_id}",
            job_id=outbox_entry.job_id,
            entity_key=outbox_entry.entity_key,
            idempotency_key=outbox_entry.idempotency_key,
            outbox_id=outbox_entry.outbox_id,
        )
        return True

    def _validate_mutating_lease(self, outbox_entry: OutboxRecord) -> bool:

        '''
        Compute lease validation result before mutating side-effect dispatch.

        Args:
        outbox_entry (OutboxRecord): Outbox entry candidate for dispatch.

        Returns:
        bool: True when lease validation passed, otherwise False.
        '''

        lease_valid = self._persistence_service.validate_job_lease_epoch(
            job_id=outbox_entry.job_id,
            expected_lease_epoch=outbox_entry.job_lease_epoch,
        )
        if lease_valid:
            return True

        self._persistence_service.append_event(
            AgentEvent(
                timestamp=_utc_now(),
                environment=outbox_entry.environment,
                trace_id=f"trc_{outbox_entry.outbox_id}",
                job_id=outbox_entry.job_id,
                entity_key=outbox_entry.entity_key,
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.BLOCKED,
                details={
                    'action': 'validate_mutating_lease',
                    'outbox_id': outbox_entry.outbox_id,
                    'expected_lease_epoch': outbox_entry.job_lease_epoch,
                    'valid': False,
                },
            )
        )
        self._persistence_service.mark_outbox_entry_aborted(
            outbox_id=outbox_entry.outbox_id,
            expected_lease_epoch=outbox_entry.lease_epoch,
            abort_reason=DISPATCHER_LEASE_VALIDATION_ABORT_REASON,
        )
        now = _utc_now()
        self._persistence_service.append_action_attempt(
            ActionAttemptRecord(
                attempt_id=self._create_attempt_id(outbox_entry),
                outbox_id=outbox_entry.outbox_id,
                job_id=outbox_entry.job_id,
                entity_key=outbox_entry.entity_key,
                environment=outbox_entry.environment,
                action_type=outbox_entry.action_type,
                status=ActionAttemptStatus.ABORTED,
                error_message=DISPATCHER_LEASE_VALIDATION_ABORT_REASON,
                attempt_started_at=now,
                attempt_completed_at=now,
            ),
        )
        current_lease_epoch = outbox_entry.job_lease_epoch
        current_job = self._persistence_service.get_job(outbox_entry.job_id)
        if current_job is not None:
            current_lease_epoch = current_job.lease_epoch

        self._alert_signal_service.emit_lease_violation(
            environment=outbox_entry.environment,
            trace_id=f"trc_{outbox_entry.outbox_id}",
            job_id=outbox_entry.job_id,
            entity_key=outbox_entry.entity_key,
            expected_lease_epoch=outbox_entry.job_lease_epoch,
            current_lease_epoch=current_lease_epoch,
        )
        return False

    def _dispatch_outbox_entry(self, outbox_entry: OutboxRecord) -> None:

        '''
        Create one side-effect dispatch attempt from outbox entry payload.

        Args:
        outbox_entry (OutboxRecord): Outbox entry for dispatch.
        '''

        payload = outbox_entry.payload
        if outbox_entry.action_type == OutboxActionType.ISSUE_COMMENT:
            self._dispatch_issue_comment(payload)
            return

        if outbox_entry.action_type == OutboxActionType.PR_REVIEW_REPLY:
            self._dispatch_pr_review_reply(payload)
            return

        message = f'Unsupported outbox action type: {outbox_entry.action_type.value}'
        raise ValueError(message)

    def _dispatch_issue_comment(self, payload: dict[str, Any]) -> None:
        repository = self._require_string(payload, 'repository')
        issue_number = self._require_int(payload, 'issue_number')
        body = self._require_string(payload, 'body')
        self._github_client.post_issue_comment(
            repository=repository,
            issue_number=issue_number,
            body=body,
        )

    def _dispatch_pr_review_reply(self, payload: dict[str, Any]) -> None:
        repository = self._require_string(payload, 'repository')
        pull_number = self._require_int(payload, 'pull_number')
        review_comment_id = self._require_int(payload, 'review_comment_id')
        body = self._require_string(payload, 'body')
        self._github_client.post_pull_review_comment_reply(
            repository=repository,
            pull_number=pull_number,
            review_comment_id=review_comment_id,
            body=body,
        )

    def _require_string(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            message = f'Outbox payload requires string field: {key}'
            raise ValueError(message)

        normalized_value = value.strip()
        if normalized_value == '':
            message = f'Outbox payload field must not be empty: {key}'
            raise ValueError(message)

        return normalized_value

    def _require_int(self, payload: dict[str, Any], key: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int):
            message = f'Outbox payload requires integer field: {key}'
            raise ValueError(message)

        if value <= 0:
            message = f'Outbox payload field must be positive: {key}'
            raise ValueError(message)

        return value


__all__ = [
    'DEFAULT_DISPATCH_BATCH_SIZE',
    'DEFAULT_RETRY_AFTER_SECONDS',
    'DISPATCHER_LEASE_VALIDATION_ABORT_REASON',
    'DISPATCHER_RECONCILIATION_ABORT_REASON',
    'OutboxDispatcher',
]
