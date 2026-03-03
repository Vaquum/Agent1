from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from agent1.core.contracts import EntityRecord
from agent1.core.contracts import EntityType
from agent1.core.contracts import EnvironmentName
from agent1.db.models import EntityModel


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for entity persistence updates.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


def _ensure_utc_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


class EntityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_entity(self, record: EntityRecord) -> EntityModel:

        '''
        Create persisted entity row from typed entity contract.

        Args:
        record (EntityRecord): Typed entity contract for persistence.

        Returns:
        EntityModel: Persisted entity model instance.
        '''

        normalized_last_event_at: datetime | None = None
        if record.last_event_at is not None:
            normalized_last_event_at = _ensure_utc_timestamp(record.last_event_at)

        model = EntityModel(
            entity_key=record.entity_key,
            repository=record.repository,
            entity_number=record.entity_number,
            entity_type=record.entity_type,
            environment=record.environment,
            is_sandbox=record.is_sandbox,
            is_closed=record.is_closed,
            last_event_at=normalized_last_event_at,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def get_entity_by_key(
        self,
        environment: EnvironmentName,
        entity_key: str,
    ) -> EntityModel | None:

        '''
        Create entity lookup result by environment-scoped entity key.

        Args:
        environment (EnvironmentName): Runtime environment value.
        entity_key (str): Durable entity key.

        Returns:
        EntityModel | None: Matching entity row or None when missing.
        '''

        return (
            self._session.query(EntityModel)
            .filter(EntityModel.environment == environment)
            .filter(EntityModel.entity_key == entity_key)
            .one_or_none()
        )

    def list_entities(
        self,
        environment: EnvironmentName,
        limit: int,
        offset: int = 0,
        repository: str | None = None,
        entity_type: EntityType | None = None,
        include_closed: bool = True,
    ) -> list[EntityModel]:

        '''
        Create entity list for environment and optional filters.

        Args:
        environment (EnvironmentName): Runtime environment value.
        limit (int): Maximum number of rows to return.
        offset (int): Pagination offset.
        repository (str | None): Optional repository filter.
        entity_type (EntityType | None): Optional entity type filter.
        include_closed (bool): Include closed rows when True.

        Returns:
        list[EntityModel]: Ordered entity rows.
        '''

        query = self._session.query(EntityModel).filter(EntityModel.environment == environment)
        if repository is not None and repository.strip() != '':
            query = query.filter(EntityModel.repository == repository.strip())
        if entity_type is not None:
            query = query.filter(EntityModel.entity_type == entity_type)
        if include_closed is False:
            query = query.filter(EntityModel.is_closed.is_(False))

        return query.order_by(EntityModel.updated_at.desc()).offset(offset).limit(limit).all()

    def count_entities(
        self,
        environment: EnvironmentName,
        repository: str | None = None,
        entity_type: EntityType | None = None,
        include_closed: bool = True,
    ) -> int:

        '''
        Create entity count for environment and optional filters.

        Args:
        environment (EnvironmentName): Runtime environment value.
        repository (str | None): Optional repository filter.
        entity_type (EntityType | None): Optional entity type filter.
        include_closed (bool): Include closed rows when True.

        Returns:
        int: Entity row count matching filters.
        '''

        query = self._session.query(EntityModel).filter(EntityModel.environment == environment)
        if repository is not None and repository.strip() != '':
            query = query.filter(EntityModel.repository == repository.strip())
        if entity_type is not None:
            query = query.filter(EntityModel.entity_type == entity_type)
        if include_closed is False:
            query = query.filter(EntityModel.is_closed.is_(False))

        return query.count()

    def touch_entity(
        self,
        environment: EnvironmentName,
        entity_key: str,
        event_timestamp: datetime,
    ) -> bool:

        '''
        Compute entity last-event update outcome by entity key.

        Args:
        environment (EnvironmentName): Runtime environment value.
        entity_key (str): Durable entity key.
        event_timestamp (datetime): Last event timestamp.

        Returns:
        bool: True when update succeeded, otherwise False.
        '''

        model = self.get_entity_by_key(environment=environment, entity_key=entity_key)
        if model is None:
            return False

        normalized_event_timestamp = _ensure_utc_timestamp(event_timestamp)
        model.last_event_at = normalized_event_timestamp
        model.updated_at = _utc_now()
        self._session.flush()
        return True


__all__ = ['EntityRepository']
