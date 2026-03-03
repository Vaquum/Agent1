from __future__ import annotations

from importlib import import_module
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config
from sqlalchemy import pool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = BACKEND_ROOT / 'src'

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _ensure_source_root_path() -> None:

    '''
    Create source-root path registration for runtime module resolution.
    '''

    source_root = str(SOURCE_ROOT)
    if source_root not in sys.path:
        sys.path.insert(0, source_root)


def _load_target_metadata():

    '''
    Create SQLAlchemy metadata loaded from runtime model modules.

    Returns:
    MetaData: SQLAlchemy metadata registry for migration autogeneration.
    '''

    _ensure_source_root_path()
    base_module = import_module('agent1.db.base')
    import_module('agent1.db.models')
    return base_module.Base.metadata


target_metadata = _load_target_metadata()


def get_database_url() -> str:

    '''
    Create database URL for migration runtime configuration.

    Returns:
    str: Database URL for Alembic migration context.
    '''

    env_url = os.getenv('DATABASE_URL')
    if env_url:
        return env_url

    config_url = config.get_main_option('sqlalchemy.url')
    if config_url:
        return config_url

    _ensure_source_root_path()
    settings_module = import_module('agent1.config.settings')
    return settings_module.get_settings().database_url


def run_migrations_offline() -> None:

    '''
    Create offline migration execution context for SQL script generation.
    '''

    database_url = get_database_url()
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:

    '''
    Create online migration execution context for direct database changes.
    '''

    configuration = config.get_section(config.config_ini_section) or {}
    configuration['sqlalchemy.url'] = get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
