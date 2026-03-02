from __future__ import annotations

from collections.abc import Callable

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.services.ingress_worker import IngressWorker


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
