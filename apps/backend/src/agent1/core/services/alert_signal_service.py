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

LEASE_VIOLATIONS_ALERT = 'lease_violations'
DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT = 'duplicate_side_effect_anomalies'
COMMENT_ROUTING_FAILURES_ALERT = 'comment_routing_failures'
OUTBOX_BACKLOG_GROWTH_ALERT = 'outbox_backlog_growth'
ELEVATED_FAILED_TRANSITION_RATES_ALERT = 'elevated_failed_transition_rates'
SEV1 = 'sev1'
SEV2 = 'sev2'
OUTBOX_BACKLOG_ALERT_THRESHOLD = 50
FAILED_TRANSITION_ALERT_THRESHOLD = 10
FAILED_TRANSITION_WINDOW_SECONDS = 300
ALERT_RUNBOOK_PATHS: dict[str, str] = {
    LEASE_VIOLATIONS_ALERT: 'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
    DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT: 'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
    COMMENT_ROUTING_FAILURES_ALERT: 'docs/Developer/runbooks/review-thread-routing-failures.md',
    OUTBOX_BACKLOG_GROWTH_ALERT: 'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
    ELEVATED_FAILED_TRANSITION_RATES_ALERT: 'docs/Developer/runbooks/github-rate-limit-and-token-failures.md',
}


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for alert signal events.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


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


__all__ = [
    'ALERT_RUNBOOK_PATHS',
    'AlertSignalService',
    'COMMENT_ROUTING_FAILURES_ALERT',
    'DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT',
    'ELEVATED_FAILED_TRANSITION_RATES_ALERT',
    'LEASE_VIOLATIONS_ALERT',
    'OUTBOX_BACKLOG_GROWTH_ALERT',
]
