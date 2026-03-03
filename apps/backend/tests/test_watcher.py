from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from agent1.core.watcher import WatcherState
from agent1.core.watcher import compute_is_watcher_stale
from agent1.core.watcher import create_next_watcher_state


def test_compute_is_watcher_stale_returns_true_when_heartbeat_old() -> None:
    now = datetime.now(timezone.utc)
    watcher_state = WatcherState(
        entity_key='Vaquum/Agent1#9',
        job_id='job_watch_1',
        next_check_at=now,
        last_heartbeat_at=now - timedelta(seconds=500),
        idle_cycles=0,
        watch_deadline_at=now + timedelta(hours=1),
        checkpoint_cursor='cursor_1',
    )

    assert compute_is_watcher_stale(watcher_state, now, stale_after_seconds=120) is True


def test_create_next_watcher_state_updates_fields() -> None:
    now = datetime.now(timezone.utc)
    watcher_state = WatcherState(
        entity_key='Vaquum/Agent1#10',
        job_id='job_watch_2',
        next_check_at=now,
        last_heartbeat_at=now,
        idle_cycles=1,
        watch_deadline_at=now + timedelta(hours=1),
        checkpoint_cursor='cursor_1',
    )
    updated_state = create_next_watcher_state(
        watcher_state=watcher_state,
        next_check_at=now + timedelta(seconds=30),
        heartbeat_at=now + timedelta(seconds=10),
        checkpoint_cursor='cursor_2',
    )

    assert updated_state.idle_cycles == 2
    assert updated_state.checkpoint_cursor == 'cursor_2'
