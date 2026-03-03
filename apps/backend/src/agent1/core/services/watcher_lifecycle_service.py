from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Sequence

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import WatcherStatus
from agent1.core.services.persistence_service import PersistenceService
from agent1.core.watcher import WatcherState

DEFAULT_WATCHER_STALE_AFTER_SECONDS = 120
DEFAULT_WATCHER_MAX_RECLAIM_ATTEMPTS = 3
DEFAULT_WATCH_DEADLINE_SECONDS = 3600


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for watcher lifecycle operations.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


class WatcherSweepResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    restored_count: int = Field(ge=0)
    reclaimed_count: int = Field(ge=0)
    operator_required_count: int = Field(ge=0)


class WatcherLifecycleService:
    def __init__(
        self,
        environment: EnvironmentName,
        watch_interval_seconds: int,
        persistence_service: PersistenceService | None = None,
        stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
        max_reclaim_attempts: int = DEFAULT_WATCHER_MAX_RECLAIM_ATTEMPTS,
        watch_deadline_seconds: int = DEFAULT_WATCH_DEADLINE_SECONDS,
    ) -> None:
        self._environment = environment
        self._watch_interval_seconds = watch_interval_seconds
        self._persistence_service = persistence_service or PersistenceService()
        self._stale_after_seconds = stale_after_seconds
        self._max_reclaim_attempts = max_reclaim_attempts
        self._watch_deadline_seconds = watch_deadline_seconds

    def track_processed_jobs(
        self,
        processed_jobs: Sequence[JobRecord],
        reference_time: datetime | None = None,
    ) -> int:

        '''
        Create persisted watcher updates for jobs touched in a worker cycle.

        Args:
        processed_jobs (Sequence[JobRecord]): Jobs touched by current worker cycle.
        reference_time (datetime | None): Optional cycle reference timestamp.

        Returns:
        int: Number of watcher rows updated.
        '''

        normalized_reference_time = _utc_now() if reference_time is None else reference_time
        updated_count = 0
        for job in processed_jobs:
            if job.state == JobState.COMPLETED:
                closed = self._persistence_service.close_watcher(
                    environment=self._environment,
                    job_id=job.job_id,
                    closed_at=normalized_reference_time,
                )
                if closed:
                    updated_count += 1
                continue

            watcher_state = WatcherState(
                entity_key=job.entity_key,
                job_id=job.job_id,
                next_check_at=normalized_reference_time + timedelta(seconds=self._watch_interval_seconds),
                last_heartbeat_at=normalized_reference_time,
                idle_cycles=0,
                watch_deadline_at=normalized_reference_time + timedelta(seconds=self._watch_deadline_seconds),
                checkpoint_cursor=job.idempotency_key,
                status=WatcherStatus.ACTIVE,
                reclaim_count=0,
                operator_required_at=None,
            )
            self._persistence_service.upsert_watcher_state(
                environment=self._environment,
                watcher_state=watcher_state,
            )
            updated_count += 1

        return updated_count

    def sweep(self, reference_time: datetime | None = None) -> WatcherSweepResult:

        '''
        Create watcher sweep result by restoring reclaimed rows and reclaiming stale rows.

        Args:
        reference_time (datetime | None): Optional cycle reference timestamp.

        Returns:
        WatcherSweepResult: Counts for restored, reclaimed, and operator-required watchers.
        '''

        normalized_reference_time = _utc_now() if reference_time is None else reference_time
        restored_count = 0
        reclaimed_count = 0
        operator_required_count = 0

        reclaimed_watchers = self._persistence_service.list_reclaimed_watchers_due(
            environment=self._environment,
            reference_time=normalized_reference_time,
        )
        for watcher_state in reclaimed_watchers:
            restored = self._persistence_service.restore_reclaimed_watcher(
                environment=self._environment,
                job_id=watcher_state.job_id,
                reference_time=normalized_reference_time,
                next_check_at=normalized_reference_time + timedelta(seconds=self._watch_interval_seconds),
            )
            if restored is not None and restored.status == WatcherStatus.ACTIVE:
                restored_count += 1

        stale_watchers = self._persistence_service.list_stale_watchers(
            environment=self._environment,
            reference_time=normalized_reference_time,
            stale_after_seconds=self._stale_after_seconds,
        )
        for watcher_state in stale_watchers:
            updated_watcher_state = self._persistence_service.mark_watcher_reclaimed(
                environment=self._environment,
                job_id=watcher_state.job_id,
                reference_time=normalized_reference_time,
                max_reclaim_attempts=self._max_reclaim_attempts,
            )
            if updated_watcher_state is None:
                continue

            if updated_watcher_state.status == WatcherStatus.OPERATOR_REQUIRED:
                operator_required_count += 1
                continue

            reclaimed_count += 1

        return WatcherSweepResult(
            restored_count=restored_count,
            reclaimed_count=reclaimed_count,
            operator_required_count=operator_required_count,
        )


__all__ = ['WatcherLifecycleService', 'WatcherSweepResult']
