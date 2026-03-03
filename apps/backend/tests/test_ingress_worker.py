from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from typing import cast

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.services.watcher_lifecycle_service import WatcherSweepResult
from agent1.core.services.ingress_worker import IngressWorker
from agent1.core.services.stop_the_line_service import StopTheLineBreach
from agent1.core.services.stop_the_line_service import StopTheLineDecision


def _create_job_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#101',
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


class _StaticProcessor:
    def process_once(self) -> list[JobRecord]:
        return [_create_job_record('job_worker_1')]


class _StopAfterOneProcessor:
    def __init__(self) -> None:
        self.calls = 0
        self.stop_callback: Callable[[], None] | None = None

    def process_once(self) -> list[JobRecord]:
        self.calls += 1
        if self.stop_callback is not None:
            self.stop_callback()
        return []


class _WatcherLifecycleService:
    def __init__(self) -> None:
        self.sweep_calls = 0
        self.track_calls = 0

    def sweep(self, reference_time: datetime | None = None) -> WatcherSweepResult:
        assert reference_time is not None
        self.sweep_calls += 1
        return WatcherSweepResult(
            restored_count=0,
            reclaimed_count=0,
            operator_required_count=0,
        )

    def track_processed_jobs(
        self,
        processed_jobs: list[JobRecord],
        reference_time: datetime | None = None,
    ) -> int:
        assert reference_time is not None
        self.track_calls += 1
        return len(processed_jobs)


class _AlertSignalService:
    def __init__(self) -> None:
        self.backlog_checks = 0
        self.failed_transition_checks = 0
        self.stop_the_line_signal_collection_calls = 0
        self.stop_the_line_alert_calls = 0

    def maybe_emit_outbox_backlog_growth(self, environment: EnvironmentName, trace_id: str) -> bool:
        assert environment == EnvironmentName.DEV
        assert trace_id != ''
        self.backlog_checks += 1
        return False

    def maybe_emit_elevated_failed_transition_rates(
        self,
        environment: EnvironmentName,
        trace_id: str,
    ) -> bool:
        assert environment == EnvironmentName.DEV
        assert trace_id != ''
        self.failed_transition_checks += 1
        return False

    def collect_stop_the_line_signal_values(
        self,
        environment: EnvironmentName,
        window_seconds: int,
    ) -> dict[str, float]:
        assert environment == EnvironmentName.DEV
        assert window_seconds == 900
        self.stop_the_line_signal_collection_calls += 1
        return {
            'error_rate': 0.10,
            'lease_violation_rate': 0.0,
            'duplicate_side_effect_rate': 0.0,
            'policy_enforcement_failure_rate': 0.0,
        }

    def maybe_emit_stop_the_line_threshold_breach(
        self,
        environment: EnvironmentName,
        trace_id: str,
        decision: StopTheLineDecision,
        signal_values: dict[str, float],
    ) -> str | None:
        assert environment == EnvironmentName.DEV
        assert trace_id != ''
        assert decision.triggered is True
        assert signal_values['error_rate'] == 0.10
        self.stop_the_line_alert_calls += 1
        return 'stop_line:trc:123'


class _StopTheLineService:
    def __init__(self) -> None:
        self.evaluate_calls = 0

    def get_evaluation_window_seconds(self) -> int:
        return 900

    def evaluate(
        self,
        signal_values: dict[str, float],
        current_mode: RuntimeMode,
    ) -> StopTheLineDecision:
        self.evaluate_calls += 1
        assert current_mode == RuntimeMode.ACTIVE
        assert signal_values['error_rate'] == 0.10
        return StopTheLineDecision(
            triggered=True,
            rollback_triggered=True,
            current_mode=RuntimeMode.ACTIVE,
            target_mode=RuntimeMode.SHADOW,
            reason='stop_the_line_triggered_mode_downgrade',
            breached_rules=[
                StopTheLineBreach(
                    signal_id='error_rate',
                    comparator='gte',
                    threshold=0.05,
                    observed_value=0.10,
                )
            ],
        )


def test_ingress_worker_process_cycle_returns_jobs() -> None:
    worker = IngressWorker(ingress_processor=_StaticProcessor(), poll_interval_seconds=1)

    processed_jobs = worker.process_cycle()

    assert len(processed_jobs) == 1
    assert processed_jobs[0].job_id == 'job_worker_1'


def test_ingress_worker_background_lifecycle_stops_gracefully() -> None:
    processor = _StopAfterOneProcessor()
    worker = IngressWorker(ingress_processor=processor, poll_interval_seconds=1)
    processor.stop_callback = worker.request_stop

    started = worker.start_background()
    worker.join(timeout_seconds=2)

    assert started is True
    assert processor.calls >= 1
    assert worker.is_running() is False


def test_ingress_worker_cycle_runs_watcher_and_alert_services() -> None:
    watcher_lifecycle_service = _WatcherLifecycleService()
    alert_signal_service = _AlertSignalService()
    worker = IngressWorker(
        ingress_processor=_StaticProcessor(),
        poll_interval_seconds=1,
        environment=EnvironmentName.DEV,
        watcher_lifecycle_service=cast(Any, watcher_lifecycle_service),
        alert_signal_service=cast(Any, alert_signal_service),
    )

    processed_jobs = worker.process_cycle()

    assert len(processed_jobs) == 1
    assert watcher_lifecycle_service.sweep_calls == 1
    assert watcher_lifecycle_service.track_calls == 1
    assert alert_signal_service.backlog_checks == 1
    assert alert_signal_service.failed_transition_checks == 1


def test_ingress_worker_cycle_evaluates_and_emits_stop_the_line_alerts() -> None:
    alert_signal_service = _AlertSignalService()
    stop_the_line_service = _StopTheLineService()
    worker = IngressWorker(
        ingress_processor=_StaticProcessor(),
        poll_interval_seconds=1,
        environment=EnvironmentName.DEV,
        runtime_mode=RuntimeMode.ACTIVE,
        alert_signal_service=cast(Any, alert_signal_service),
        stop_the_line_service=cast(Any, stop_the_line_service),
    )

    processed_jobs = worker.process_cycle()

    assert len(processed_jobs) == 1
    assert stop_the_line_service.evaluate_calls == 1
    assert alert_signal_service.stop_the_line_signal_collection_calls == 1
    assert alert_signal_service.stop_the_line_alert_calls == 1
