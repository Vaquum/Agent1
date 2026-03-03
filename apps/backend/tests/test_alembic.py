from pathlib import Path

from alembic import command
from alembic.config import Config
from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy import create_engine
from sqlalchemy import inspect


def test_alembic_upgrade_head_creates_core_tables(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_ini_path = backend_root / 'alembic.ini'
    database_path = tmp_path / 'migration_test.db'
    database_url = f'sqlite+pysqlite:///{database_path}'

    monkeypatch.delenv('DATABASE_URL', raising=False)

    config = Config(str(alembic_ini_path))
    config.set_main_option('script_location', str(backend_root / 'alembic'))
    config.set_main_option('sqlalchemy.url', database_url)

    command.upgrade(config, 'head')

    engine = create_engine(database_url, future=True)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

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
