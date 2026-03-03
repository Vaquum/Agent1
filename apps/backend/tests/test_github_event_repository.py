from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import IngressOrderingDecision
from agent1.db.models import GitHubEventModel
from agent1.db.models import IngressEntityCursorModel
from agent1.db.repositories.github_event_repository import GitHubEventRepository
from agent1.db.repositories.github_event_repository import STALE_REASON_DUPLICATE_EVENT_ID
from agent1.db.repositories.github_event_repository import STALE_REASON_OLDER_TIMESTAMP
from agent1.db.repositories.github_event_repository import STALE_REASON_TIE_BREAKER


def _create_ingress_event(
    event_id: str,
    timestamp: datetime,
) -> GitHubIngressEvent:
    return GitHubIngressEvent(
        event_id=event_id,
        repository='Vaquum/Agent1',
        entity_number=601,
        entity_type=IngressEntityType.ISSUE,
        actor='mikkokotila',
        event_type=IngressEventType.ISSUE_MENTION,
        timestamp=timestamp,
        details={},
    )


def test_github_event_repository_persists_ordering_fields_and_high_water(
    session_factory: sessionmaker[Session],
) -> None:
    timestamp = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = GitHubEventRepository(session)
        persisted_event = repository.persist_ingress_event(
            ingress_event=_create_ingress_event('evt_ordering_1', timestamp),
            environment=EnvironmentName.DEV,
        )
        session.commit()

    with session_factory() as verification_session:
        persisted_rows = verification_session.query(GitHubEventModel).all()
        cursor_rows = verification_session.query(IngressEntityCursorModel).all()

    assert len(persisted_rows) == 1
    assert len(cursor_rows) == 1
    assert persisted_event.source_event_id == 'evt_ordering_1'
    assert persisted_event.source_timestamp_or_seq == timestamp.isoformat()
    assert persisted_event.ordering_decision == IngressOrderingDecision.ACCEPTED
    assert cursor_rows[0].high_water_source_event_id == 'evt_ordering_1'


def test_github_event_repository_marks_stale_older_timestamp_event(
    session_factory: sessionmaker[Session],
) -> None:
    newer_timestamp = datetime(2026, 3, 5, 12, 1, tzinfo=timezone.utc)
    older_timestamp = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = GitHubEventRepository(session)
        repository.persist_ingress_event(
            ingress_event=_create_ingress_event('evt_ordering_2', newer_timestamp),
            environment=EnvironmentName.DEV,
        )
        stale_event = repository.persist_ingress_event(
            ingress_event=_create_ingress_event('evt_ordering_3', older_timestamp),
            environment=EnvironmentName.DEV,
        )
        session.commit()

    with session_factory() as verification_session:
        cursor = verification_session.query(IngressEntityCursorModel).one()
        stale_rows = (
            verification_session.query(GitHubEventModel)
            .filter(GitHubEventModel.is_stale.is_(True))
            .all()
        )

    assert stale_event.ordering_decision == IngressOrderingDecision.STALE
    assert stale_event.stale_reason == STALE_REASON_OLDER_TIMESTAMP
    assert cursor.high_water_source_event_id == 'evt_ordering_2'
    assert len(stale_rows) == 1


def test_github_event_repository_marks_stale_tie_breaker_and_duplicate_events(
    session_factory: sessionmaker[Session],
) -> None:
    timestamp = datetime(2026, 3, 5, 12, 2, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = GitHubEventRepository(session)
        repository.persist_ingress_event(
            ingress_event=_create_ingress_event('evt_ordering_b', timestamp),
            environment=EnvironmentName.DEV,
        )
        tie_breaker_stale_event = repository.persist_ingress_event(
            ingress_event=_create_ingress_event('evt_ordering_a', timestamp),
            environment=EnvironmentName.DEV,
        )
        duplicate_stale_event = repository.persist_ingress_event(
            ingress_event=_create_ingress_event('evt_ordering_b', timestamp),
            environment=EnvironmentName.DEV,
        )
        session.commit()

    assert tie_breaker_stale_event.ordering_decision == IngressOrderingDecision.STALE
    assert tie_breaker_stale_event.stale_reason == STALE_REASON_TIE_BREAKER
    assert duplicate_stale_event.ordering_decision == IngressOrderingDecision.STALE
    assert duplicate_stale_event.stale_reason == STALE_REASON_DUPLICATE_EVENT_ID
