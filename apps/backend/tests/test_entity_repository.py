from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EntityRecord
from agent1.core.contracts import EntityType
from agent1.core.contracts import EnvironmentName
from agent1.db.repositories.entity_repository import EntityRepository


def _create_record(entity_key: str, entity_type: EntityType = EntityType.ISSUE) -> EntityRecord:
    return EntityRecord(
        entity_key=entity_key,
        repository='Vaquum/Agent1',
        entity_number=100,
        entity_type=entity_type,
        environment=EnvironmentName.DEV,
        is_sandbox=True,
        is_closed=False,
    )


def test_entity_repository_create_and_get_entity(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        repository = EntityRepository(session)
        repository.create_entity(_create_record('Vaquum/Agent1#100'))
        session.commit()

    with session_factory() as verification_session:
        repository = EntityRepository(verification_session)
        entity = repository.get_entity_by_key(
            environment=EnvironmentName.DEV,
            entity_key='Vaquum/Agent1#100',
        )

    assert entity is not None
    assert entity.repository == 'Vaquum/Agent1'
    assert entity.entity_type == EntityType.ISSUE
    assert entity.is_sandbox is True


def test_entity_repository_list_count_and_touch_entity(session_factory: sessionmaker[Session]) -> None:
    now = datetime(2026, 3, 4, 21, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = EntityRepository(session)
        repository.create_entity(_create_record('Vaquum/Agent1#101', EntityType.ISSUE))
        repository.create_entity(
            EntityRecord(
                entity_key='Vaquum/Agent1#102',
                repository='Vaquum/Agent1',
                entity_number=102,
                entity_type=EntityType.PR,
                environment=EnvironmentName.DEV,
                is_sandbox=False,
                is_closed=True,
                last_event_at=now - timedelta(seconds=10),
            ),
        )
        session.commit()

    with session_factory() as filtered_session:
        repository = EntityRepository(filtered_session)
        open_entities = repository.list_entities(
            environment=EnvironmentName.DEV,
            limit=10,
            include_closed=False,
        )
        pr_entities = repository.list_entities(
            environment=EnvironmentName.DEV,
            limit=10,
            entity_type=EntityType.PR,
        )
        entity_count = repository.count_entities(
            environment=EnvironmentName.DEV,
            include_closed=False,
        )
        touched = repository.touch_entity(
            environment=EnvironmentName.DEV,
            entity_key='Vaquum/Agent1#101',
            event_timestamp=now,
        )
        filtered_session.commit()

    with session_factory() as verification_session:
        repository = EntityRepository(verification_session)
        touched_entity = repository.get_entity_by_key(
            environment=EnvironmentName.DEV,
            entity_key='Vaquum/Agent1#101',
        )

    assert len(open_entities) == 1
    assert len(pr_entities) == 1
    assert entity_count == 1
    assert touched is True
    assert touched_entity is not None
    assert touched_entity.last_event_at is not None
