from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from time import monotonic
from typing import Protocol

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobRecord
from agent1.core.services.alert_signal_service import AlertSignalService
from agent1.core.services.telemetry_runtime import get_tracer
from agent1.core.services.trace_context import create_trace_id
from agent1.core.services.trace_context import reset_trace_id
from agent1.core.services.trace_context import set_trace_id
from agent1.core.services.watcher_lifecycle_service import WatcherLifecycleService

WORKER_LOGGER_NAME = 'agent1.worker'
WORKER_JOIN_TIMEOUT_SECONDS = 5


class IngressProcessor(Protocol):
    def process_once(self) -> list[JobRecord]:
        ...


class IngressWorker:
    def __init__(
        self,
        ingress_processor: IngressProcessor,
        poll_interval_seconds: int,
        environment: EnvironmentName = EnvironmentName.DEV,
        watcher_lifecycle_service: WatcherLifecycleService | None = None,
        alert_signal_service: AlertSignalService | None = None,
    ) -> None:
        self._ingress_processor = ingress_processor
        self._poll_interval_seconds = poll_interval_seconds
        self._environment = environment
        self._watcher_lifecycle_service = watcher_lifecycle_service
        self._alert_signal_service = alert_signal_service
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._logger = logging.getLogger(WORKER_LOGGER_NAME)

    def process_cycle(self) -> Sequence[JobRecord]:

        '''
        Create one worker cycle result by executing ingress processing once.

        Returns:
        Sequence[JobRecord]: Jobs touched by current cycle.
        '''

        trace_id = create_trace_id()
        token = set_trace_id(trace_id)
        try:
            with get_tracer().start_as_current_span('ingress.worker.process_cycle') as span:
                cycle_reference_time = datetime.now(timezone.utc)
                if self._watcher_lifecycle_service is not None:
                    watcher_sweep_result = self._watcher_lifecycle_service.sweep(cycle_reference_time)
                    span.set_attribute(
                        'agent1.worker.watchers_reclaimed_count',
                        watcher_sweep_result.reclaimed_count,
                    )
                    span.set_attribute(
                        'agent1.worker.watchers_restored_count',
                        watcher_sweep_result.restored_count,
                    )
                    span.set_attribute(
                        'agent1.worker.watchers_operator_required_count',
                        watcher_sweep_result.operator_required_count,
                    )

                processed_jobs = self._ingress_processor.process_once()
                if self._watcher_lifecycle_service is not None:
                    tracked_count = self._watcher_lifecycle_service.track_processed_jobs(
                        processed_jobs=processed_jobs,
                        reference_time=cycle_reference_time,
                    )
                    span.set_attribute('agent1.worker.watchers_tracked_count', tracked_count)

                if self._alert_signal_service is not None:
                    self._alert_signal_service.maybe_emit_outbox_backlog_growth(
                        environment=self._environment,
                        trace_id=trace_id,
                    )
                    self._alert_signal_service.maybe_emit_elevated_failed_transition_rates(
                        environment=self._environment,
                        trace_id=trace_id,
                    )

                span.set_attribute('agent1.worker.jobs_processed_count', len(processed_jobs))
                self._logger.info(
                    'worker_cycle_complete trace_id=%s jobs_processed=%s',
                    trace_id,
                    len(processed_jobs),
                )
                return processed_jobs
        except Exception:
            self._logger.exception('worker_cycle_failed trace_id=%s', trace_id)
            return []
        finally:
            reset_trace_id(token)

    def run_loop(self) -> None:

        '''
        Create continuous worker loop until stop request is received.
        '''

        while self._stop_event.is_set() is False:
            started_at = monotonic()
            self.process_cycle()
            elapsed_seconds = monotonic() - started_at
            wait_seconds = max(self._poll_interval_seconds - elapsed_seconds, 0)
            self._stop_event.wait(wait_seconds)

    def start_background(self) -> bool:

        '''
        Create background worker thread and start loop when not already active.

        Returns:
        bool: True when worker thread started, otherwise False.
        '''

        if self.is_running():
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_loop, name='agent1-ingress-worker', daemon=True)
        self._thread.start()
        return True

    def request_stop(self) -> None:

        '''
        Create stop request signal for worker thread loop termination.
        '''

        self._stop_event.set()

    def join(self, timeout_seconds: float = WORKER_JOIN_TIMEOUT_SECONDS) -> None:

        '''
        Create worker join wait for graceful thread shutdown completion.

        Args:
        timeout_seconds (float): Maximum wait duration for worker thread join.
        '''

        if self._thread is None:
            return

        self._thread.join(timeout=timeout_seconds)

    def is_running(self) -> bool:

        '''
        Create worker running-state lookup.

        Returns:
        bool: True when worker thread exists and is alive.
        '''

        return self._thread is not None and self._thread.is_alive()


__all__ = ['IngressProcessor', 'IngressWorker']
