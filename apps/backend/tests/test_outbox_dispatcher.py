from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.adapters.github.client import GitHubApiClient
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxRecord
from agent1.core.contracts import OutboxStatus
from agent1.core.contracts import OutboxWriteRequest
from agent1.core.contracts import RuntimeMode
from agent1.core.services.alert_signal_service import DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT
from agent1.core.services.alert_signal_service import LEASE_VIOLATIONS_ALERT
from agent1.core.services.alert_signal_service import OUTBOX_BACKLOG_GROWTH_ALERT
from agent1.core.services.alert_signal_service import AlertSignalService
from agent1.core.services.outbox_dispatcher import OutboxDispatcher
from agent1.core.services.persistence_service import PersistenceService
from agent1.db.models import EventJournalModel


class _FakeGitHubClient(GitHubApiClient):
    def __init__(self, fail_issue_comment: bool = False) -> None:
        self.issue_comments: list[tuple[str, int, str]] = []
        self.review_replies: list[tuple[str, int, int, str]] = []
        self._fail_issue_comment = fail_issue_comment

    def fetch_notifications(
        self,
        since: datetime | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, object]]:
        _ = since
        _ = page
        _ = per_page
        return []

    def fetch_pull_request_timeline(self, repository: str, pull_number: int) -> list[dict[str, object]]:
        _ = repository
        _ = pull_number
        return []

    def fetch_pull_request_check_runs(self, repository: str, pull_number: int) -> list[dict[str, object]]:
        _ = repository
        _ = pull_number
        return []

    def fetch_issue(self, repository: str, issue_number: int) -> dict[str, object]:
        _ = repository
        _ = issue_number
        return {}

    def fetch_pull_request(self, repository: str, pull_number: int) -> dict[str, object]:
        _ = repository
        _ = pull_number
        return {}

    def post_issue_comment(self, repository: str, issue_number: int, body: str) -> dict[str, object]:
        if self._fail_issue_comment:
            raise RuntimeError('issue_comment_failure')

        self.issue_comments.append((repository, issue_number, body))
        return {}

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        self.review_replies.append((repository, pull_number, review_comment_id, body))
        return {}


def _create_job_record(job_id: str, entity_key: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key=entity_key,
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'{job_id}_idem',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def test_outbox_dispatcher_confirms_issue_comment_entry(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    created_job = persistence_service.create_job(
        _create_job_record(
            job_id='job_outbox_dispatch_1',
            entity_key='Vaquum/Agent1#510',
        ),
    )
    created_outbox = persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_dispatch_1',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#510:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 510,
                'body': 'dispatch hello',
            },
            idempotency_key='outbox_dispatch_idem_1',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    github_client = _FakeGitHubClient()
    dispatcher = OutboxDispatcher(
        persistence_service=persistence_service,
        github_client=github_client,
    )

    confirmed_count = dispatcher.dispatch_once()
    persisted_outbox = persistence_service.get_outbox_entry_by_outbox_id(created_outbox.outbox_id)

    assert confirmed_count == 1
    assert github_client.issue_comments == [('Vaquum/Agent1', 510, 'dispatch hello')]
    assert persisted_outbox is not None
    assert persisted_outbox.status == OutboxStatus.CONFIRMED
    assert persisted_outbox.attempt_count == 1
    assert persisted_outbox.lease_epoch == 2


def test_outbox_dispatcher_marks_failed_issue_comment_entry(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    created_job = persistence_service.create_job(
        _create_job_record(
            job_id='job_outbox_dispatch_2',
            entity_key='Vaquum/Agent1#511',
        ),
    )
    created_outbox = persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_dispatch_2',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#511:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 511,
                'body': 'dispatch fail',
            },
            idempotency_key='outbox_dispatch_idem_2',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    github_client = _FakeGitHubClient(fail_issue_comment=True)
    dispatcher = OutboxDispatcher(
        persistence_service=persistence_service,
        github_client=github_client,
        retry_after_seconds=5,
    )

    confirmed_count = dispatcher.dispatch_once()
    persisted_outbox = persistence_service.get_outbox_entry_by_outbox_id(created_outbox.outbox_id)

    assert confirmed_count == 0
    assert github_client.issue_comments == []
    assert persisted_outbox is not None
    assert persisted_outbox.status == OutboxStatus.FAILED
    assert persisted_outbox.attempt_count == 1
    assert persisted_outbox.lease_epoch == 2
    assert persisted_outbox.last_error == 'issue_comment_failure'
    assert persisted_outbox.next_attempt_at is not None


def test_outbox_dispatcher_confirms_pr_review_reply_entry(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    created_job = persistence_service.create_job(
        _create_job_record(
            job_id='job_outbox_dispatch_3',
            entity_key='Vaquum/Agent1#512',
        ),
    )
    created_outbox = persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_dispatch_3',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.PR_REVIEW_REPLY,
            target_identity='Vaquum/Agent1#512:review:600',
            payload={
                'repository': 'Vaquum/Agent1',
                'pull_number': 512,
                'review_comment_id': 600,
                'body': 'review reply',
            },
            idempotency_key='outbox_dispatch_idem_3',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    github_client = _FakeGitHubClient()
    dispatcher = OutboxDispatcher(
        persistence_service=persistence_service,
        github_client=github_client,
    )

    confirmed_count = dispatcher.dispatch_once()
    persisted_outbox = persistence_service.get_outbox_entry_by_outbox_id(created_outbox.outbox_id)

    assert confirmed_count == 1
    assert github_client.review_replies == [('Vaquum/Agent1', 512, 600, 'review reply')]
    assert persisted_outbox is not None
    assert persisted_outbox.status == OutboxStatus.CONFIRMED


def test_outbox_dispatcher_aborts_when_job_lease_is_stale(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    created_job = persistence_service.create_job(
        _create_job_record(
            job_id='job_outbox_dispatch_4',
            entity_key='Vaquum/Agent1#513',
        ),
    )
    created_outbox = persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_dispatch_4',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#513:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 513,
                'body': 'dispatch stale lease',
            },
            idempotency_key='outbox_dispatch_idem_4',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    persistence_service.claim_job_lease(created_job.job_id, expected_lease_epoch=0)
    github_client = _FakeGitHubClient()
    dispatcher = OutboxDispatcher(
        persistence_service=persistence_service,
        github_client=github_client,
    )

    confirmed_count = dispatcher.dispatch_once()
    persisted_outbox = persistence_service.get_outbox_entry_by_outbox_id(created_outbox.outbox_id)
    with session_factory() as verification_session:
        alert_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('alert_name') == LEASE_VIOLATIONS_ALERT
        ]

    assert confirmed_count == 0
    assert github_client.issue_comments == []
    assert persisted_outbox is not None
    assert persisted_outbox.status == OutboxStatus.ABORTED
    assert len(alert_events) == 1


def test_outbox_dispatcher_emits_duplicate_side_effect_anomaly_alert(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    created_job = persistence_service.create_job(
        _create_job_record(
            job_id='job_outbox_dispatch_5',
            entity_key='Vaquum/Agent1#514',
        ),
    )
    created_outbox = persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_dispatch_5',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#514:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 514,
                'body': 'dispatch duplicate anomaly',
            },
            idempotency_key='outbox_dispatch_idem_5',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    persistence_service.mark_outbox_entry_sent(
        outbox_id=created_outbox.outbox_id,
        expected_lease_epoch=created_outbox.lease_epoch,
    )
    persistence_service.mark_outbox_entry_failed(
        outbox_id=created_outbox.outbox_id,
        expected_lease_epoch=created_outbox.lease_epoch + 1,
        error_message='retry_me',
        retry_after_seconds=0,
    )

    def _fake_scope_lookup(
        environment: EnvironmentName,
        action_type: OutboxActionType,
        target_identity: str,
        idempotency_key: str,
    ) -> OutboxRecord:
        return OutboxRecord(
            outbox_id='outbox_dispatch_5_confirmed_shadow',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=environment,
            action_type=action_type,
            target_identity=target_identity,
            payload={},
            idempotency_key=idempotency_key,
            job_lease_epoch=0,
            status=OutboxStatus.CONFIRMED,
            attempt_count=1,
            lease_epoch=0,
            next_attempt_at=None,
            last_attempt_at=None,
            last_error=None,
        )

    monkeypatch.setattr(
        persistence_service,
        'get_outbox_entry_by_idempotency_scope',
        _fake_scope_lookup,
    )
    dispatcher = OutboxDispatcher(
        persistence_service=persistence_service,
        github_client=_FakeGitHubClient(),
    )

    confirmed_count = dispatcher.dispatch_once()
    persisted_outbox = persistence_service.get_outbox_entry_by_outbox_id(created_outbox.outbox_id)
    with session_factory() as verification_session:
        alert_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('alert_name') == DUPLICATE_SIDE_EFFECT_ANOMALIES_ALERT
        ]

    assert confirmed_count == 0
    assert persisted_outbox is not None
    assert persisted_outbox.status == OutboxStatus.ABORTED
    assert len(alert_events) == 1


def test_outbox_dispatcher_emits_backlog_growth_alert(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    created_job = persistence_service.create_job(
        _create_job_record(
            job_id='job_outbox_dispatch_6',
            entity_key='Vaquum/Agent1#515',
        ),
    )
    persistence_service.append_outbox_entry(
        OutboxWriteRequest(
            outbox_id='outbox_dispatch_6',
            job_id=created_job.job_id,
            entity_key=created_job.entity_key,
            environment=created_job.environment,
            action_type=OutboxActionType.ISSUE_COMMENT,
            target_identity='Vaquum/Agent1#515:issue',
            payload={
                'repository': 'Vaquum/Agent1',
                'issue_number': 515,
                'body': 'dispatch backlog alert',
            },
            idempotency_key='outbox_dispatch_idem_6',
            job_lease_epoch=created_job.lease_epoch,
        ),
    )
    alert_signal_service = AlertSignalService(
        persistence_service=persistence_service,
        outbox_backlog_alert_threshold=1,
    )
    dispatcher = OutboxDispatcher(
        persistence_service=persistence_service,
        github_client=_FakeGitHubClient(),
        alert_signal_service=alert_signal_service,
    )

    dispatcher.dispatch_once()
    with session_factory() as verification_session:
        alert_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('alert_name') == OUTBOX_BACKLOG_GROWTH_ALERT
        ]

    assert len(alert_events) == 1
