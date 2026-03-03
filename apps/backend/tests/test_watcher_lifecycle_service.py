from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.contracts import WatcherStatus
from agent1.core.services.persistence_service import PersistenceService
from agent1.core.services.watcher_lifecycle_service import WatcherLifecycleService
from agent1.core.watcher import WatcherState


def _create_job_record(job_id: str, state: JobState = JobState.READY_TO_EXECUTE) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#950',
        kind=JobKind.ISSUE,
        state=state,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_watcher_lifecycle_tracks_processed_jobs(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_watch_lifecycle_1'))
    lifecycle_service = WatcherLifecycleService(
        environment=EnvironmentName.DEV,
        watch_interval_seconds=30,
        persistence_service=persistence_service,
        stale_after_seconds=120,
        max_reclaim_attempts=3,
        watch_deadline_seconds=600,
    )
    now = datetime(2026, 3, 4, 18, 0, tzinfo=timezone.utc)

    tracked_count = lifecycle_service.track_processed_jobs(
        processed_jobs=[_create_job_record('job_watch_lifecycle_1')],
        reference_time=now,
    )
    stale_watchers = persistence_service.list_stale_watchers(
        environment=EnvironmentName.DEV,
        reference_time=now + timedelta(seconds=10),
        stale_after_seconds=60,
    )

    assert tracked_count == 1
    assert len(stale_watchers) == 0


def test_watcher_lifecycle_reclaims_and_restores_from_checkpoint(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_watch_lifecycle_2'))
    now = datetime(2026, 3, 4, 19, 0, tzinfo=timezone.utc)
    persistence_service.upsert_watcher_state(
        environment=EnvironmentName.DEV,
        watcher_state=WatcherState(
            entity_key='Vaquum/Agent1#950',
            job_id='job_watch_lifecycle_2',
            next_check_at=now - timedelta(seconds=10),
            last_heartbeat_at=now - timedelta(seconds=500),
            idle_cycles=1,
            watch_deadline_at=now + timedelta(seconds=5),
            checkpoint_cursor='cursor_lifecycle',
            status=WatcherStatus.ACTIVE,
            reclaim_count=0,
        ),
    )
    lifecycle_service = WatcherLifecycleService(
        environment=EnvironmentName.DEV,
        watch_interval_seconds=30,
        persistence_service=persistence_service,
        stale_after_seconds=120,
        max_reclaim_attempts=3,
        watch_deadline_seconds=600,
    )

    first_sweep = lifecycle_service.sweep(reference_time=now)
    second_sweep = lifecycle_service.sweep(reference_time=now + timedelta(seconds=1))
    active_count = persistence_service.count_watchers_by_status(
        environment=EnvironmentName.DEV,
        status=WatcherStatus.ACTIVE,
    )

    assert first_sweep.reclaimed_count == 1
    assert first_sweep.operator_required_count == 0
    assert second_sweep.restored_count == 1
    assert active_count == 1


def test_watcher_lifecycle_escalates_to_operator_required_for_stuck_watchers(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_watch_lifecycle_2b'))
    now = datetime(2026, 3, 4, 19, 30, tzinfo=timezone.utc)
    persistence_service.upsert_watcher_state(
        environment=EnvironmentName.DEV,
        watcher_state=WatcherState(
            entity_key='Vaquum/Agent1#950',
            job_id='job_watch_lifecycle_2b',
            next_check_at=now - timedelta(seconds=10),
            last_heartbeat_at=now - timedelta(seconds=500),
            idle_cycles=1,
            watch_deadline_at=now + timedelta(seconds=5),
            checkpoint_cursor='cursor_escalate',
            status=WatcherStatus.ACTIVE,
            reclaim_count=0,
        ),
    )
    lifecycle_service = WatcherLifecycleService(
        environment=EnvironmentName.DEV,
        watch_interval_seconds=30,
        persistence_service=persistence_service,
        stale_after_seconds=120,
        max_reclaim_attempts=1,
        watch_deadline_seconds=600,
    )

    sweep_result = lifecycle_service.sweep(reference_time=now)
    operator_required_count = persistence_service.count_watchers_by_status(
        environment=EnvironmentName.DEV,
        status=WatcherStatus.OPERATOR_REQUIRED,
    )

    assert sweep_result.operator_required_count == 1
    assert operator_required_count == 1


def test_watcher_lifecycle_closes_watcher_for_completed_jobs(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    persistence_service.create_job(_create_job_record('job_watch_lifecycle_3', state=JobState.COMPLETED))
    lifecycle_service = WatcherLifecycleService(
        environment=EnvironmentName.DEV,
        watch_interval_seconds=30,
        persistence_service=persistence_service,
    )
    now = datetime(2026, 3, 4, 20, 0, tzinfo=timezone.utc)
    persistence_service.upsert_watcher_state(
        environment=EnvironmentName.DEV,
        watcher_state=WatcherState(
            entity_key='Vaquum/Agent1#950',
            job_id='job_watch_lifecycle_3',
            next_check_at=now + timedelta(seconds=30),
            last_heartbeat_at=now,
            idle_cycles=0,
            watch_deadline_at=now + timedelta(minutes=5),
            checkpoint_cursor='cursor_completed',
            status=WatcherStatus.ACTIVE,
            reclaim_count=0,
        ),
    )

    tracked_count = lifecycle_service.track_processed_jobs(
        processed_jobs=[_create_job_record('job_watch_lifecycle_3', state=JobState.COMPLETED)],
        reference_time=now + timedelta(seconds=1),
    )
    closed_count = persistence_service.count_watchers_by_status(
        environment=EnvironmentName.DEV,
        status=WatcherStatus.CLOSED,
    )

    assert tracked_count == 1
    assert closed_count == 1
