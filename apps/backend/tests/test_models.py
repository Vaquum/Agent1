from agent1.db.base import Base
import agent1.db.models as _models


def test_metadata_contains_core_tables() -> None:
    assert _models is not None

    table_names = set(Base.metadata.tables.keys())

    assert 'jobs' in table_names
    assert 'job_transitions' in table_names
    assert 'event_journal' in table_names
    assert 'ingestion_cursors' in table_names
    assert 'outbox_entries' in table_names
    assert 'github_events' in table_names
    assert 'ingress_entity_cursors' in table_names
    assert 'watcher_states' in table_names
