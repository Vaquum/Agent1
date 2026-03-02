from agent1.db.base import Base
from agent1.db import models as _models


def test_metadata_contains_core_tables() -> None:
    assert _models is not None

    table_names = set(Base.metadata.tables.keys())

    assert 'jobs' in table_names
    assert 'job_transitions' in table_names
    assert 'event_journal' in table_names
    assert 'ingestion_cursors' in table_names
