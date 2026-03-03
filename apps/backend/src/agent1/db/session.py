from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.config.settings import get_settings


def create_db_engine() -> Engine:

    '''
    Create SQLAlchemy engine from configured database URL.

    Returns:
    Engine: SQLAlchemy database engine.
    '''

    settings = get_settings()
    return create_engine(settings.database_url, future=True)


def create_session_factory() -> sessionmaker[Session]:

    '''
    Create SQLAlchemy session factory for transactional data access.

    Returns:
    sessionmaker[Session]: Configured SQLAlchemy session factory.
    '''

    return sessionmaker(bind=create_db_engine(), autoflush=False, autocommit=False)


__all__ = ['create_db_engine', 'create_session_factory']
