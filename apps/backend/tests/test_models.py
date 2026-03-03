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
    assert 'entities' in table_names
    assert 'action_attempts' in table_names
    assert 'comment_targets' in table_names
    outbox_columns = set(Base.metadata.tables['outbox_entries'].columns.keys())
    assert 'idempotency_schema_version' in outbox_columns
    assert 'idempotency_payload_hash' in outbox_columns
    assert 'idempotency_policy_version_hash' in outbox_columns
    event_columns = set(Base.metadata.tables['event_journal'].columns.keys())
    assert 'event_seq' in event_columns
    assert 'prev_event_hash' in event_columns
    assert 'payload_hash' in event_columns
