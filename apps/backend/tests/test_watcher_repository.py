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
from agent1.core.watcher import WatcherState
from agent1.db.repositories.job_repository import JobRepository
from agent1.db.repositories.watcher_repository import WatcherRepository


def _create_job_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#901',
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_watcher_repository_upsert_and_list_stale_watchers(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 3, 4, 16, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        job_repository = JobRepository(session)
        watcher_repository = WatcherRepository(session)
        job_repository.create_job(_create_job_record('job_watch_repo_1'))
        watcher_repository.upsert_watcher_state(
            environment=EnvironmentName.DEV,
            watcher_state=WatcherState(
                entity_key='Vaquum/Agent1#901',
                job_id='job_watch_repo_1',
                next_check_at=now + timedelta(seconds=30),
                last_heartbeat_at=now - timedelta(seconds=200),
                idle_cycles=2,
                watch_deadline_at=now + timedelta(hours=1),
                checkpoint_cursor='cursor_901',
                status=WatcherStatus.ACTIVE,
                reclaim_count=0,
            ),
        )
        session.commit()

    with session_factory() as verification_session:
        repository = WatcherRepository(verification_session)
        stale_watchers = repository.list_stale_watchers(
            environment=EnvironmentName.DEV,
            reference_time=now,
            stale_after_seconds=120,
        )

    assert len(stale_watchers) == 1
    assert stale_watchers[0].job_id == 'job_watch_repo_1'
    assert stale_watchers[0].checkpoint_cursor == 'cursor_901'


def test_watcher_repository_reclaim_restore_and_operator_required(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 3, 4, 17, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        job_repository = JobRepository(session)
        watcher_repository = WatcherRepository(session)
        job_repository.create_job(_create_job_record('job_watch_repo_2'))
        watcher_repository.upsert_watcher_state(
            environment=EnvironmentName.DEV,
            watcher_state=WatcherState(
                entity_key='Vaquum/Agent1#901',
                job_id='job_watch_repo_2',
                next_check_at=now,
                last_heartbeat_at=now - timedelta(seconds=180),
                idle_cycles=0,
                watch_deadline_at=now + timedelta(minutes=5),
                checkpoint_cursor='cursor_restore',
                status=WatcherStatus.ACTIVE,
                reclaim_count=0,
            ),
        )
        session.commit()

    with session_factory() as reclaim_session:
        repository = WatcherRepository(reclaim_session)
        reclaimed = repository.mark_watcher_reclaimed(
            environment=EnvironmentName.DEV,
            job_id='job_watch_repo_2',
            reference_time=now,
            max_reclaim_attempts=3,
        )
        reclaimed_status = reclaimed.status if reclaimed is not None else None
        reclaim_session.commit()

    with session_factory() as restore_session:
        repository = WatcherRepository(restore_session)
        due_watchers = repository.list_reclaimed_watchers_due(
            environment=EnvironmentName.DEV,
            reference_time=now + timedelta(seconds=1),
        )
        restored = repository.restore_reclaimed_watcher(
            environment=EnvironmentName.DEV,
            job_id='job_watch_repo_2',
            reference_time=now + timedelta(seconds=1),
            next_check_at=now + timedelta(seconds=31),
        )
        restored_status = restored.status if restored is not None else None
        restore_session.commit()

    with session_factory() as operator_session:
        repository = WatcherRepository(operator_session)
        escalated = repository.mark_watcher_reclaimed(
            environment=EnvironmentName.DEV,
            job_id='job_watch_repo_2',
            reference_time=now + timedelta(seconds=2),
            max_reclaim_attempts=1,
        )
        escalated_status = escalated.status if escalated is not None else None
        operator_count = repository.count_watchers_by_status(
            environment=EnvironmentName.DEV,
            status=WatcherStatus.OPERATOR_REQUIRED,
        )
        operator_session.commit()

    assert reclaimed is not None
    assert reclaimed_status == WatcherStatus.RECLAIMED
    assert len(due_watchers) == 1
    assert restored is not None
    assert restored_status == WatcherStatus.ACTIVE
    assert escalated is not None
    assert escalated_status == WatcherStatus.OPERATOR_REQUIRED
    assert operator_count == 1
