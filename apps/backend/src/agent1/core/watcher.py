from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.contracts import WatcherStatus


class WatcherState(BaseModel):
    model_config = ConfigDict(extra='forbid')

    entity_key: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    next_check_at: datetime
    last_heartbeat_at: datetime
    idle_cycles: int = Field(ge=0)
    watch_deadline_at: datetime
    checkpoint_cursor: str | None = None
    status: WatcherStatus = WatcherStatus.ACTIVE
    reclaim_count: int = Field(ge=0, default=0)
    operator_required_at: datetime | None = None


def compute_is_watcher_stale(
    watcher_state: WatcherState,
    reference_time: datetime,
    stale_after_seconds: int,
) -> bool:

    '''
    Compute whether watcher heartbeat has exceeded stale threshold.

    Args:
    watcher_state (WatcherState): Current watcher state snapshot.
    reference_time (datetime): Current timestamp used for comparison.
    stale_after_seconds (int): Allowed heartbeat age in seconds.

    Returns:
    bool: True when watcher is stale, otherwise False.
    '''

    heartbeat_age_seconds = (
        reference_time - watcher_state.last_heartbeat_at
    ).total_seconds()
    return heartbeat_age_seconds > stale_after_seconds


def create_next_watcher_state(
    watcher_state: WatcherState,
    next_check_at: datetime,
    heartbeat_at: datetime,
    checkpoint_cursor: str | None = None,
    idle_increment: int = 1,
) -> WatcherState:

    '''
    Create next watcher state snapshot with heartbeat/checkpoint updates.

    Args:
    watcher_state (WatcherState): Current watcher state snapshot.
    next_check_at (datetime): Next scheduled check timestamp.
    heartbeat_at (datetime): New heartbeat timestamp.
    checkpoint_cursor (str | None): Optional updated checkpoint cursor.
    idle_increment (int): Idle cycle increment value.

    Returns:
    WatcherState: Updated watcher state snapshot.
    '''

    return watcher_state.model_copy(
        update={
            'next_check_at': next_check_at,
            'last_heartbeat_at': heartbeat_at,
            'idle_cycles': watcher_state.idle_cycles + idle_increment,
            'checkpoint_cursor': checkpoint_cursor or watcher_state.checkpoint_cursor,
        }
    )


__all__ = [
    'WatcherState',
    'compute_is_watcher_stale',
    'create_next_watcher_state',
]
