from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import WatcherStatus
from agent1.core.watcher import WatcherState
from agent1.db.models import WatcherStateModel


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for watcher persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class WatcherRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_watcher_by_job_id(
        self,
        environment: EnvironmentName,
        job_id: str,
    ) -> WatcherStateModel | None:

        '''
        Create watcher lookup result by environment and job identifier.

        Args:
        environment (EnvironmentName): Runtime environment value.
        job_id (str): Durable job identifier.

        Returns:
        WatcherStateModel | None: Matching watcher row or None when missing.
        '''

        return (
            self._session.query(WatcherStateModel)
            .filter(WatcherStateModel.environment == environment)
            .filter(WatcherStateModel.job_id == job_id)
            .one_or_none()
        )

    def upsert_watcher_state(
        self,
        environment: EnvironmentName,
        watcher_state: WatcherState,
    ) -> WatcherStateModel:

        '''
        Create persisted watcher row by inserting or updating state fields.

        Args:
        environment (EnvironmentName): Runtime environment value.
        watcher_state (WatcherState): Typed watcher state payload.

        Returns:
        WatcherStateModel: Persisted watcher row.
        '''

        model = self.get_watcher_by_job_id(environment, watcher_state.job_id)
        normalized_next_check_at = _ensure_utc_timestamp(watcher_state.next_check_at)
        normalized_last_heartbeat_at = _ensure_utc_timestamp(watcher_state.last_heartbeat_at)
        normalized_watch_deadline_at = _ensure_utc_timestamp(watcher_state.watch_deadline_at)
        normalized_operator_required_at: datetime | None = None
        if watcher_state.operator_required_at is not None:
            normalized_operator_required_at = _ensure_utc_timestamp(watcher_state.operator_required_at)

        if model is None:
            model = WatcherStateModel(
                environment=environment,
                job_id=watcher_state.job_id,
                entity_key=watcher_state.entity_key,
                next_check_at=normalized_next_check_at,
                last_heartbeat_at=normalized_last_heartbeat_at,
                idle_cycles=watcher_state.idle_cycles,
                watch_deadline_at=normalized_watch_deadline_at,
                checkpoint_cursor=watcher_state.checkpoint_cursor,
                status=watcher_state.status,
                reclaim_count=watcher_state.reclaim_count,
                operator_required_at=normalized_operator_required_at,
            )
            self._session.add(model)
            self._session.flush()
            return model

        model.entity_key = watcher_state.entity_key
        model.next_check_at = normalized_next_check_at
        model.last_heartbeat_at = normalized_last_heartbeat_at
        model.idle_cycles = watcher_state.idle_cycles
        model.watch_deadline_at = normalized_watch_deadline_at
        model.checkpoint_cursor = watcher_state.checkpoint_cursor
        model.status = watcher_state.status
        model.reclaim_count = watcher_state.reclaim_count
        model.operator_required_at = normalized_operator_required_at
        model.updated_at = _utc_now()
        self._session.flush()
        return model

    def list_stale_watchers(
        self,
        environment: EnvironmentName,
        reference_time: datetime,
        stale_after_seconds: int,
    ) -> list[WatcherStateModel]:

        '''
        Create stale watcher list eligible for reclaim operations.

        Args:
        environment (EnvironmentName): Runtime environment value.
        reference_time (datetime): Current reference timestamp.
        stale_after_seconds (int): Allowed heartbeat age before stale status.

        Returns:
        list[WatcherStateModel]: Ordered stale watcher rows.
        '''

        stale_before_timestamp = _ensure_utc_timestamp(reference_time) - timedelta(seconds=stale_after_seconds)
        return (
            self._session.query(WatcherStateModel)
            .filter(WatcherStateModel.environment == environment)
            .filter(
                WatcherStateModel.status.in_(
                    [
                        WatcherStatus.ACTIVE,
                        WatcherStatus.RECLAIMED,
                    ],
                ),
            )
            .filter(WatcherStateModel.last_heartbeat_at <= stale_before_timestamp)
            .order_by(WatcherStateModel.last_heartbeat_at.asc())
            .all()
        )

    def list_reclaimed_watchers_due(
        self,
        environment: EnvironmentName,
        reference_time: datetime,
    ) -> list[WatcherStateModel]:

        '''
        Create reclaimed watcher list due for checkpoint restoration.

        Args:
        environment (EnvironmentName): Runtime environment value.
        reference_time (datetime): Current reference timestamp.

        Returns:
        list[WatcherStateModel]: Ordered reclaimed watcher rows due now.
        '''

        normalized_reference_time = _ensure_utc_timestamp(reference_time)
        return (
            self._session.query(WatcherStateModel)
            .filter(WatcherStateModel.environment == environment)
            .filter(WatcherStateModel.status == WatcherStatus.RECLAIMED)
            .filter(WatcherStateModel.next_check_at <= normalized_reference_time)
            .order_by(WatcherStateModel.next_check_at.asc())
            .all()
        )

    def mark_watcher_reclaimed(
        self,
        environment: EnvironmentName,
        job_id: str,
        reference_time: datetime,
        max_reclaim_attempts: int,
    ) -> WatcherStateModel | None:

        '''
        Create stale watcher reclaim update and operator-required escalation when needed.

        Args:
        environment (EnvironmentName): Runtime environment value.
        job_id (str): Durable job identifier.
        reference_time (datetime): Current reference timestamp.
        max_reclaim_attempts (int): Maximum reclaim attempts before escalation.

        Returns:
        WatcherStateModel | None: Updated watcher row or None when missing.
        '''

        model = self.get_watcher_by_job_id(environment, job_id)
        if model is None:
            return None

        normalized_reference_time = _ensure_utc_timestamp(reference_time)
        next_reclaim_count = model.reclaim_count + 1
        normalized_watch_deadline_at = _ensure_utc_timestamp(model.watch_deadline_at)
        operator_required = (
            next_reclaim_count >= max_reclaim_attempts
            or normalized_reference_time >= normalized_watch_deadline_at
        )
        model.reclaim_count = next_reclaim_count
        model.idle_cycles = model.idle_cycles + 1
        model.last_heartbeat_at = normalized_reference_time
        model.next_check_at = normalized_reference_time
        model.updated_at = normalized_reference_time
        if operator_required:
            model.status = WatcherStatus.OPERATOR_REQUIRED
            model.operator_required_at = normalized_reference_time
            model.last_reclaimed_at = normalized_reference_time
        else:
            model.status = WatcherStatus.RECLAIMED
            model.last_reclaimed_at = normalized_reference_time
            model.operator_required_at = None

        self._session.flush()
        return model

    def restore_reclaimed_watcher(
        self,
        environment: EnvironmentName,
        job_id: str,
        reference_time: datetime,
        next_check_at: datetime,
    ) -> WatcherStateModel | None:

        '''
        Create checkpoint restoration update for reclaimed watcher rows.

        Args:
        environment (EnvironmentName): Runtime environment value.
        job_id (str): Durable job identifier.
        reference_time (datetime): Current reference timestamp.
        next_check_at (datetime): Next check timestamp after restoration.

        Returns:
        WatcherStateModel | None: Updated watcher row or None when missing.
        '''

        model = self.get_watcher_by_job_id(environment, job_id)
        if model is None:
            return None

        if model.status != WatcherStatus.RECLAIMED:
            return model

        normalized_reference_time = _ensure_utc_timestamp(reference_time)
        model.status = WatcherStatus.ACTIVE
        model.last_heartbeat_at = normalized_reference_time
        model.next_check_at = _ensure_utc_timestamp(next_check_at)
        model.updated_at = normalized_reference_time
        self._session.flush()
        return model

    def close_watcher(
        self,
        environment: EnvironmentName,
        job_id: str,
        closed_at: datetime,
    ) -> bool:

        '''
        Compute close-state update outcome for one watcher row.

        Args:
        environment (EnvironmentName): Runtime environment value.
        job_id (str): Durable job identifier.
        closed_at (datetime): Close timestamp.

        Returns:
        bool: True when close-state update succeeded, otherwise False.
        '''

        model = self.get_watcher_by_job_id(environment, job_id)
        if model is None:
            return False

        normalized_closed_at = _ensure_utc_timestamp(closed_at)
        model.status = WatcherStatus.CLOSED
        model.last_heartbeat_at = normalized_closed_at
        model.next_check_at = normalized_closed_at
        model.updated_at = normalized_closed_at
        self._session.flush()
        return True

    def count_watchers_by_status(
        self,
        environment: EnvironmentName,
        status: WatcherStatus,
    ) -> int:

        '''
        Create watcher row count for one status value.

        Args:
        environment (EnvironmentName): Runtime environment value.
        status (WatcherStatus): Watcher status value.

        Returns:
        int: Watcher row count matching status.
        '''

        return (
            self._session.query(WatcherStateModel)
            .filter(WatcherStateModel.environment == environment)
            .filter(WatcherStateModel.status == status)
            .count()
        )


__all__ = ['WatcherRepository']
