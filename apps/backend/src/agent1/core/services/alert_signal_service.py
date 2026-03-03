from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from agent1.core.contracts import AgentEvent
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EventSource
from agent1.core.contracts import EventStatus
from agent1.core.contracts import EventType
from agent1.core.services.persistence_service import PersistenceService
from agent1.core.services.stop_the_line_service import StopTheLineDecision

LEASE_VIOLATIONS_ALERT = 'lease_violations'
DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT = 'duplicate_side_effect_anomalies'
COMMENT_ROUTING_FAILURES_ALERT = 'comment_routing_failures'
OUTBOX_BACKLOG_GROWTH_ALERT = 'outbox_backlog_growth'
ELEVATED_FAILED_TRANSITION_RATES_ALERT = 'elevated_failed_transition_rates'
STOP_THE_LINE_THRESHOLD_BREACH_ALERT = 'stop_the_line_threshold_breach'
HASH_CHAIN_GAP_ANOMALIES_ALERT = 'hash_chain_gap_anomalies'
IDEMPOTENCY_SCOPE_VIOLATIONS_ALERT = 'idempotency_scope_violations'
STOP_THE_LINE_SYSTEM_JOB_ID = 'system:stop_the_line'
STOP_THE_LINE_SYSTEM_ENTITY_KEY = 'system:stop_the_line'
EVENT_CHAIN_SYSTEM_JOB_ID = 'system:event_chain'
EVENT_CHAIN_SYSTEM_ENTITY_KEY = 'system:event_chain'
IDEMPOTENCY_SYSTEM_JOB_ID = 'system:idempotency'
IDEMPOTENCY_SYSTEM_ENTITY_KEY = 'system:idempotency'
SEV1 = 'sev1'
SEV2 = 'sev2'
OUTBOX_BACKLOG_ALERT_THRESHOLD = 50
FAILED_TRANSITION_ALERT_THRESHOLD = 10
FAILED_TRANSITION_WINDOW_SECONDS = 300
EVENT_CHAIN_FINDING_SAMPLE_LIMIT = 5
IDEMPOTENCY_SCOPE_VIOLATION_SAMPLE_LIMIT = 10
ALERT_RUNBOOK_PATHS: dict[str, str] = {
    LEASE_VIOLATIONS_ALERT: 'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
    DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT: 'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
    COMMENT_ROUTING_FAILURES_ALERT: 'docs/Developer/runbooks/review-thread-routing-failures.md',
    OUTBOX_BACKLOG_GROWTH_ALERT: 'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
    ELEVATED_FAILED_TRANSITION_RATES_ALERT: 'docs/Developer/runbooks/github-rate-limit-and-token-failures.md',
    STOP_THE_LINE_THRESHOLD_BREACH_ALERT: 'docs/Developer/runbooks/stop-the-line-alerts.md',
    HASH_CHAIN_GAP_ANOMALIES_ALERT: 'docs/Developer/runbooks/event-journal-chain-validation.md',
    IDEMPOTENCY_SCOPE_VIOLATIONS_ALERT: 'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
}


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for alert signal events.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _create_stop_the_line_alert_id(trace_id: str, timestamp: datetime) -> str:

    '''
    Create deterministic stop-the-line alert identifier from trace and emission timestamp.

    Args:
    trace_id (str): Correlation trace identifier.
    timestamp (datetime): Alert emission timestamp.

    Returns:
    str: Deterministic stop-the-line alert identifier.
    '''

    return f'stop_line:{trace_id}:{int(timestamp.timestamp() * 1000)}'


class AlertSignalService:
    def __init__(
        self,
        persistence_service: PersistenceService | None = None,
        outbox_backlog_alert_threshold: int = OUTBOX_BACKLOG_ALERT_THRESHOLD,
        failed_transition_alert_threshold: int = FAILED_TRANSITION_ALERT_THRESHOLD,
        failed_transition_window_seconds: int = FAILED_TRANSITION_WINDOW_SECONDS,
    ) -> None:
        self._persistence_service = persistence_service or PersistenceService()
        self._outbox_backlog_alert_threshold = outbox_backlog_alert_threshold
        self._failed_transition_alert_threshold = failed_transition_alert_threshold
        self._failed_transition_window_seconds = failed_transition_window_seconds

    def collect_stop_the_line_signal_values(
        self,
        environment: EnvironmentName,
        window_seconds: int,
    ) -> dict[str, float]:

        '''
        Create stop-the-line signal values from recent persisted operational events.

        Args:
        environment (EnvironmentName): Runtime environment value.
        window_seconds (int): Inclusive event window size in seconds.

        Returns:
        dict[str, float]: Computed stop-the-line signal values keyed by signal identifier.
        '''

        window_start = _utc_now() - timedelta(seconds=window_seconds)
        recent_events = self._persistence_service.list_events_since(
            environment=environment,
            window_start=window_start,
        )
        transition_count = 0
        failed_transition_count = 0
        policy_api_call_count = 0
        lease_violation_count = 0
        duplicate_side_effect_count = 0
        policy_enforcement_failure_count = 0

        for event in recent_events:
            if event.event_type == EventType.STATE_TRANSITION:
                transition_count += 1
                if event.status in {EventStatus.BLOCKED, EventStatus.ERROR}:
                    failed_transition_count += 1

            if event.source != EventSource.POLICY or event.event_type != EventType.API_CALL:
                continue

            action = event.details.get('action')
            if isinstance(action, str) and action in {
                'emit_alert_signal',
                'acknowledge_stop_the_line_alert',
            }:
                continue

            policy_api_call_count += 1
            reason = event.details.get('reason')
            if isinstance(reason, str):
                if reason == 'mutating_lease_validation_failed':
                    lease_violation_count += 1
                elif reason == 'outbox_reconciliation_detected_confirmed_duplicate':
                    duplicate_side_effect_count += 1

                if reason.startswith('policy_') or reason == 'codex_git_command_policy_blocked':
                    policy_enforcement_failure_count += 1

        transition_denominator = max(transition_count, 1)
        policy_denominator = max(policy_api_call_count, 1)
        return {
            'error_rate': failed_transition_count / transition_denominator,
            'lease_violation_rate': lease_violation_count / policy_denominator,
            'duplicate_side_effect_rate': duplicate_side_effect_count / policy_denominator,
            'policy_enforcement_failure_rate': policy_enforcement_failure_count / policy_denominator,
        }

    def emit_alert_signal(
        self,
        environment: EnvironmentName,
        alert_name: str,
        severity: str,
        trace_id: str,
        job_id: str,
        entity_key: str,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:

        '''
        Create operational alert signal event with required payload fields.

        Args:
        environment (EnvironmentName): Runtime environment value.
        alert_name (str): Deterministic alert identifier.
        severity (str): Alert severity label.
        trace_id (str): Correlation trace identifier.
        job_id (str): Durable job identifier.
        entity_key (str): Entity key associated with the alert.
        reason (str): Deterministic alert reason.
        details (dict[str, Any] | None): Optional additional alert metadata.
        '''

        runbook = ALERT_RUNBOOK_PATHS[alert_name]
        event_details = details.copy() if details is not None else {}
        event_details.update(
            {
                'action': 'emit_alert_signal',
                'alert_name': alert_name,
                'severity': severity,
                'reason': reason,
                'runbook': runbook,
                'trace_id': trace_id,
                'job_id': job_id,
            },
        )
        self._persistence_service.append_event(
            AgentEvent(
                timestamp=_utc_now(),
                environment=environment,
                trace_id=trace_id,
                job_id=job_id,
                entity_key=entity_key,
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.ERROR,
                details=event_details,
            ),
        )

    def emit_lease_violation(
        self,
        environment: EnvironmentName,
        trace_id: str,
        job_id: str,
        entity_key: str,
        expected_lease_epoch: int,
        current_lease_epoch: int,
    ) -> None:

        '''
        Create lease-violation alert signal with deterministic lease metadata.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.
        job_id (str): Durable job identifier.
        entity_key (str): Entity key associated with the alert.
        expected_lease_epoch (int): Expected lease epoch value.
        current_lease_epoch (int): Current lease epoch value.
        '''

        self.emit_alert_signal(
            environment=environment,
            alert_name=LEASE_VIOLATIONS_ALERT,
            severity=SEV1,
            trace_id=trace_id,
            job_id=job_id,
            entity_key=entity_key,
            reason='mutating_lease_validation_failed',
            details={
                'expected_lease_epoch': expected_lease_epoch,
                'current_lease_epoch': current_lease_epoch,
            },
        )

    def emit_duplicate_side_effect_anomaly(
        self,
        environment: EnvironmentName,
        trace_id: str,
        job_id: str,
        entity_key: str,
        idempotency_key: str,
        outbox_id: str,
    ) -> None:

        '''
        Create duplicate-side-effect anomaly alert signal for outbox reconciliation.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.
        job_id (str): Durable job identifier.
        entity_key (str): Entity key associated with the alert.
        idempotency_key (str): Deterministic idempotency key.
        outbox_id (str): Durable outbox identifier.
        '''

        self.emit_alert_signal(
            environment=environment,
            alert_name=DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT,
            severity=SEV1,
            trace_id=trace_id,
            job_id=job_id,
            entity_key=entity_key,
            reason='outbox_reconciliation_detected_confirmed_duplicate',
            details={
                'idempotency_key': idempotency_key,
                'outbox_id': outbox_id,
            },
        )

    def emit_comment_routing_failure(
        self,
        environment: EnvironmentName,
        trace_id: str,
        job_id: str,
        entity_key: str,
        error_message: str,
    ) -> None:

        '''
        Create comment-routing failure alert signal with deterministic error metadata.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.
        job_id (str): Durable job identifier.
        entity_key (str): Entity key associated with the alert.
        error_message (str): Deterministic routing failure summary.
        '''

        self.emit_alert_signal(
            environment=environment,
            alert_name=COMMENT_ROUTING_FAILURES_ALERT,
            severity=SEV1,
            trace_id=trace_id,
            job_id=job_id,
            entity_key=entity_key,
            reason='comment_routing_failure',
            details={'error_message': error_message},
        )

    def maybe_emit_outbox_backlog_growth(
        self,
        environment: EnvironmentName,
        trace_id: str,
    ) -> bool:

        '''
        Compute outbox backlog alert emission when backlog exceeds configured threshold.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.

        Returns:
        bool: True when alert was emitted, otherwise False.
        '''

        backlog_count = self._persistence_service.count_outbox_backlog()
        if backlog_count < self._outbox_backlog_alert_threshold:
            return False

        self.emit_alert_signal(
            environment=environment,
            alert_name=OUTBOX_BACKLOG_GROWTH_ALERT,
            severity=SEV2,
            trace_id=trace_id,
            job_id='system:outbox',
            entity_key='system:outbox',
            reason='outbox_backlog_threshold_exceeded',
            details={
                'backlog_count': backlog_count,
                'threshold': self._outbox_backlog_alert_threshold,
            },
        )
        return True

    def maybe_emit_elevated_failed_transition_rates(
        self,
        environment: EnvironmentName,
        trace_id: str,
    ) -> bool:

        '''
        Compute failed-transition-rate alert emission for recent transition event window.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.

        Returns:
        bool: True when alert was emitted, otherwise False.
        '''

        window_start = _utc_now() - timedelta(seconds=self._failed_transition_window_seconds)
        failed_transition_count = self._persistence_service.count_recent_failed_transition_events(window_start)
        if failed_transition_count < self._failed_transition_alert_threshold:
            return False

        self.emit_alert_signal(
            environment=environment,
            alert_name=ELEVATED_FAILED_TRANSITION_RATES_ALERT,
            severity=SEV2,
            trace_id=trace_id,
            job_id='system:transitions',
            entity_key='system:transitions',
            reason='failed_transition_rate_threshold_exceeded',
            details={
                'failed_transition_count': failed_transition_count,
                'threshold': self._failed_transition_alert_threshold,
                'window_seconds': self._failed_transition_window_seconds,
            },
        )
        return True

    def maybe_emit_hash_chain_gap_anomalies(
        self,
        environment: EnvironmentName,
        trace_id: str,
    ) -> bool:

        '''
        Compute event-journal hash-chain anomaly alert emission for one environment.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.

        Returns:
        bool: True when alert was emitted, otherwise False.
        '''

        findings = self._persistence_service.verify_event_chain(environment=environment)
        if len(findings) == 0:
            return False

        self.emit_alert_signal(
            environment=environment,
            alert_name=HASH_CHAIN_GAP_ANOMALIES_ALERT,
            severity=SEV1,
            trace_id=trace_id,
            job_id=EVENT_CHAIN_SYSTEM_JOB_ID,
            entity_key=EVENT_CHAIN_SYSTEM_ENTITY_KEY,
            reason='event_journal_chain_validation_failed',
            details={
                'finding_count': len(findings),
                'findings': findings[:EVENT_CHAIN_FINDING_SAMPLE_LIMIT],
            },
        )
        return True

    def maybe_emit_idempotency_scope_violations(
        self,
        environment: EnvironmentName,
        trace_id: str,
    ) -> bool:

        '''
        Compute idempotency-scope violation alert emission for one environment.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.

        Returns:
        bool: True when alert was emitted, otherwise False.
        '''

        violations = self._persistence_service.list_idempotency_scope_violations(
            environment=environment,
            limit=IDEMPOTENCY_SCOPE_VIOLATION_SAMPLE_LIMIT,
        )
        if len(violations) == 0:
            return False

        self.emit_alert_signal(
            environment=environment,
            alert_name=IDEMPOTENCY_SCOPE_VIOLATIONS_ALERT,
            severity=SEV1,
            trace_id=trace_id,
            job_id=IDEMPOTENCY_SYSTEM_JOB_ID,
            entity_key=IDEMPOTENCY_SYSTEM_ENTITY_KEY,
            reason='idempotency_scope_violation_detected',
            details={
                'violation_count': len(violations),
                'violations': [
                    {
                        'idempotency_key': violation.idempotency_key,
                        'entry_count': violation.entry_count,
                        'outbox_ids': violation.outbox_ids,
                        'scopes': violation.scopes,
                    }
                    for violation in violations
                ],
            },
        )
        return True

    def maybe_emit_stop_the_line_threshold_breach(
        self,
        environment: EnvironmentName,
        trace_id: str,
        decision: StopTheLineDecision,
        signal_values: dict[str, float],
    ) -> str | None:

        '''
        Create stop-the-line threshold-breach alert event when decision indicates trigger state.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.
        decision (StopTheLineDecision): Stop-the-line decision payload.
        signal_values (dict[str, float]): Evaluated signal values used for decision.

        Returns:
        str | None: Emitted alert identifier when triggered, otherwise None.
        '''

        if decision.triggered is False:
            return None

        emitted_at = _utc_now()
        alert_id = _create_stop_the_line_alert_id(trace_id=trace_id, timestamp=emitted_at)
        self.emit_alert_signal(
            environment=environment,
            alert_name=STOP_THE_LINE_THRESHOLD_BREACH_ALERT,
            severity=SEV1,
            trace_id=trace_id,
            job_id=STOP_THE_LINE_SYSTEM_JOB_ID,
            entity_key=STOP_THE_LINE_SYSTEM_ENTITY_KEY,
            reason=decision.reason,
            details={
                'action': 'stop_the_line_threshold_breach',
                'alert_id': alert_id,
                'current_mode': decision.current_mode.value,
                'target_mode': decision.target_mode.value,
                'rollback_triggered': decision.rollback_triggered,
                'signal_values': signal_values,
                'breached_rules': [rule.model_dump(mode='json') for rule in decision.breached_rules],
            },
        )
        return alert_id

    def acknowledge_stop_the_line_alert(
        self,
        environment: EnvironmentName,
        trace_id: str,
        alert_id: str,
        operator_id: str,
        acknowledgement_note: str,
    ) -> datetime:

        '''
        Create operator acknowledgement event for one emitted stop-the-line alert identifier.

        Args:
        environment (EnvironmentName): Runtime environment value.
        trace_id (str): Correlation trace identifier.
        alert_id (str): Emitted stop-the-line alert identifier.
        operator_id (str): Operator identity acknowledging the alert.
        acknowledgement_note (str): Deterministic operator acknowledgement summary.

        Returns:
        datetime: Acknowledgement timestamp.
        '''

        acknowledged_at = _utc_now()
        runbook = ALERT_RUNBOOK_PATHS[STOP_THE_LINE_THRESHOLD_BREACH_ALERT]
        self._persistence_service.append_event(
            AgentEvent(
                timestamp=acknowledged_at,
                environment=environment,
                trace_id=trace_id,
                job_id=STOP_THE_LINE_SYSTEM_JOB_ID,
                entity_key=STOP_THE_LINE_SYSTEM_ENTITY_KEY,
                source=EventSource.POLICY,
                event_type=EventType.API_CALL,
                status=EventStatus.OK,
                details={
                    'action': 'acknowledge_stop_the_line_alert',
                    'alert_name': STOP_THE_LINE_THRESHOLD_BREACH_ALERT,
                    'alert_id': alert_id,
                    'operator_id': operator_id,
                    'acknowledgement_note': acknowledgement_note,
                    'runbook': runbook,
                    'trace_id': trace_id,
                    'job_id': STOP_THE_LINE_SYSTEM_JOB_ID,
                },
            ),
        )
        return acknowledged_at


__all__ = [
    'ALERT_RUNBOOK_PATHS',
    'AlertSignalService',
    'COMMENT_ROUTING_FAILURES_ALERT',
    'DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT',
    'ELEVATED_FAILED_TRANSITION_RATES_ALERT',
    'HASH_CHAIN_GAP_ANOMALIES_ALERT',
    'IDEMPOTENCY_SCOPE_VIOLATIONS_ALERT',
    'LEASE_VIOLATIONS_ALERT',
    'OUTBOX_BACKLOG_GROWTH_ALERT',
    'STOP_THE_LINE_THRESHOLD_BREACH_ALERT',
]
