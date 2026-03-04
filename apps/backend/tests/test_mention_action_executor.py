from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxStatus
from agent1.core.contracts import RuntimeMode
from agent1.core.contracts import CommentTargetType
from agent1.core.ingress_contracts import NormalizedIngressEvent
from agent1.core.orchestrator import JobOrchestrator
from agent1.core.services.alert_signal_service import COMMENT_ROUTING_FAILURES_ALERT
from agent1.core.services.alert_signal_service import LEASE_VIOLATIONS_ALERT
from agent1.core.services.idempotency_schema import build_canonical_idempotency_key
from agent1.core.services.mention_action_executor import MentionActionExecutor
from agent1.core.services.persistence_service import PersistenceService
from agent1.db.models import CommentTargetModel
from agent1.db.models import EventJournalModel
from agent1.db.models import OutboxEntryModel


def _create_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#25',
        kind=JobKind.ISSUE,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def _create_reviewer_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#25',
        kind=JobKind.PR_REVIEWER,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def _create_author_record(job_id: str) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#25',
        kind=JobKind.PR_AUTHOR,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def _create_record_with_state(job_id: str, state: JobState) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#25',
        kind=JobKind.ISSUE,
        state=state,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=RuntimeMode.ACTIVE,
    )


def _create_record_with_mode(job_id: str, mode: RuntimeMode, kind: JobKind = JobKind.ISSUE) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        entity_key='Vaquum/Agent1#25',
        kind=kind,
        state=JobState.READY_TO_EXECUTE,
        idempotency_key=f'idem_{job_id}',
        lease_epoch=0,
        environment=EnvironmentName.DEV,
        mode=mode,
    )


def _create_normalized_event(
    ingress_event_type: str,
    details: dict[str, object] | None = None,
    job_kind: JobKind = JobKind.ISSUE,
    job_id: str = 'Vaquum_Agent1#25:issue',
) -> NormalizedIngressEvent:
    return NormalizedIngressEvent(
        event_id='evt_mention_1',
        trace_id='trc_evt_mention_1',
        environment=EnvironmentName.DEV,
        repository='Vaquum/Agent1',
        entity_number=25,
        entity_key='Vaquum/Agent1#25',
        job_id=job_id,
        job_kind=job_kind,
        initial_state=JobState.READY_TO_EXECUTE,
        should_claim_lease=True,
        transition_to=JobState.READY_TO_EXECUTE,
        transition_reason='issue_mention',
        idempotency_key='evt_mention_1:issue_mention',
        details={
            'ingress_event_type': ingress_event_type,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **(details or {}),
        },
    )


def _create_reviewer_pull_request_files() -> list[dict[str, object]]:
    return [
        {
            'filename': 'apps/backend/src/agent1/main.py',
            'patch': (
                '@@ -1,3 +1,4 @@\n'
                ' line_one\n'
                '+line_two\n'
                ' line_three\n'
            ),
        },
        {
            'filename': 'apps/backend/src/agent1/core/services/comment_router.py',
            'patch': (
                '@@ -10,3 +10,4 @@\n'
                ' line_a\n'
                '+line_b\n'
                ' line_c\n'
            ),
        },
    ]


def _create_reviewer_inline_payload(summary: str) -> str:
    return json.dumps(
        {
            'summary': summary,
            'comments': [
                {
                    'path': 'apps/backend/src/agent1/main.py',
                    'line': 2,
                    'side': 'RIGHT',
                    'body': 'Inline finding one.',
                },
                {
                    'path': 'apps/backend/src/agent1/core/services/comment_router.py',
                    'line': 11,
                    'side': 'RIGHT',
                    'body': 'Inline finding two.',
                },
            ],
        }
    )


class _FakeGitHubClient:
    def __init__(
        self,
        should_fail: bool = False,
        issue_payload: dict[str, object] | None = None,
        pull_request_payload: dict[str, object] | None = None,
        pull_request_files: list[dict[str, object]] | None = None,
    ) -> None:
        self._should_fail = should_fail
        self._issue_payload = issue_payload or {}
        self._pull_request_payload = pull_request_payload or {}
        self._pull_request_files = pull_request_files or []
        self.comment_calls: list[dict[str, object]] = []
        self.thread_reply_calls: list[dict[str, object]] = []
        self.review_submission_calls: list[dict[str, object]] = []

    def fetch_notifications(
        self,
        since: datetime | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict[str, object]]:
        return []

    def fetch_pull_request_timeline(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return []

    def fetch_pull_request_check_runs(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        return []

    def fetch_issue(
        self,
        repository: str,
        issue_number: int,
    ) -> dict[str, object]:
        return dict(self._issue_payload)

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:
        _ = repository
        _ = pull_number
        return dict(self._pull_request_payload)

    def fetch_pull_request_files(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        _ = repository
        _ = pull_number
        return [dict(payload) for payload in self._pull_request_files]

    def post_issue_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:
        self.comment_calls.append(
            {
                'repository': repository,
                'issue_number': issue_number,
                'body': body,
            }
        )
        if self._should_fail:
            raise RuntimeError('comment failure')

        return {'id': 1, 'body': body}

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        self.thread_reply_calls.append(
            {
                'repository': repository,
                'pull_number': pull_number,
                'review_comment_id': review_comment_id,
                'body': body,
            }
        )
        if self._should_fail:
            raise RuntimeError('comment failure')

        return {'id': review_comment_id, 'body': body}

    def submit_pull_request_review(
        self,
        repository: str,
        pull_number: int,
        body: str,
        event: str = 'COMMENT',
        comments: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        self.review_submission_calls.append(
            {
                'repository': repository,
                'pull_number': pull_number,
                'body': body,
                'event': event,
                'comments': comments,
            }
        )
        if self._should_fail:
            raise RuntimeError('comment failure')

        return {'id': 1, 'body': body, 'event': event}


class _FakeCodexExecutor:
    def __init__(
        self,
        status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
        last_message: str = 'codex output',
    ) -> None:
        self._status = status
        self._last_message = last_message
        self.execute_calls: list[dict[str, object]] = []

    def execute_task(
        self,
        task_id: str,
        prompt: str,
        arguments: list[str] | None = None,
        working_directory: str | None = None,
        timeout_seconds: int | None = None,
        environment: dict[str, str] | None = None,
        event_handler: object | None = None,
    ) -> ExecutionResult:
        self.execute_calls.append(
            {
                'task_id': task_id,
                'prompt': prompt,
                'arguments': arguments,
                'working_directory': working_directory,
                'timeout_seconds': timeout_seconds,
                'environment': environment,
                'event_handler': event_handler,
            }
        )
        return ExecutionResult(
            status=self._status,
            summary='codex execution',
            command='codex exec',
            exit_code=0 if self._status == ExecutionStatus.SUCCEEDED else 1,
            metadata={'last_message': self._last_message},
        )


def test_mention_action_executor_posts_comment_and_advances_state(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient(
        issue_payload={'body': 'Respond "hello world" if you see this message.'},
    )
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event('issue_mention'),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        comment_targets = verification_session.query(CommentTargetModel).all()
        outbox_entries = verification_session.query(OutboxEntryModel).all()

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'hello world'
    assert updated.state == JobState.COMPLETED
    assert len(comment_targets) == 1
    assert comment_targets[0].target_type == CommentTargetType.ISSUE
    assert len(outbox_entries) == 1
    assert outbox_entries[0].status == OutboxStatus.CONFIRMED
    assert outbox_entries[0].idempotency_schema_version == 'v1'
    assert outbox_entries[0].idempotency_payload_hash is not None
    assert outbox_entries[0].idempotency_policy_version_hash is not None
    assert outbox_entries[0].idempotency_key == build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#25',
        action_type=outbox_entries[0].action_type,
        target_identity=outbox_entries[0].target_identity,
        payload=outbox_entries[0].payload,
        policy_version='unversioned',
    )


def test_mention_action_executor_handles_issue_updated_resume_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event('issue_updated'),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'Need clarification for Vaquum/Agent1#25'
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_requests_clarification_without_directive(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient(issue_payload={'body': 'Please help me with this issue.'})
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event('issue_mention'),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'Need clarification for Vaquum/Agent1#25'
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_uses_policy_version_for_idempotency_key(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue_policy'), trace_id='trc_create')
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        idempotency_policy_version='0.1.0',
        github_client=fake_client,
    )

    executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'issue_mention',
            job_id='Vaquum_Agent1#25:issue_policy',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        outbox_entry = verification_session.query(OutboxEntryModel).one()

    assert outbox_entry.idempotency_key == build_canonical_idempotency_key(
        entity_key='Vaquum/Agent1#25',
        action_type=outbox_entry.action_type,
        target_identity=outbox_entry.target_identity,
        payload=outbox_entry.payload,
        policy_version='0.1.0',
    )


def test_mention_action_executor_handles_reviewer_request_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_reviewer_record('Vaquum_Agent1#25:pr_reviewer'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient(
        pull_request_files=_create_reviewer_pull_request_files(),
    )
    fake_codex = _FakeCodexExecutor(
        last_message=_create_reviewer_inline_payload('Reviewer summary A'),
    )
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_review_requested',
            job_kind=JobKind.PR_REVIEWER,
            job_id='Vaquum_Agent1#25:pr_reviewer',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.review_submission_calls) == 1
    assert fake_client.review_submission_calls[0]['body'] == 'Reviewer summary A'
    assert fake_client.review_submission_calls[0]['event'] == 'COMMENT'
    review_comments = fake_client.review_submission_calls[0]['comments']
    assert isinstance(review_comments, list)
    assert len(review_comments) == 2
    assert review_comments[0]['path'] == 'apps/backend/src/agent1/main.py'
    assert review_comments[0]['line'] == 2
    assert review_comments[1]['path'] == 'apps/backend/src/agent1/core/services/comment_router.py'
    assert review_comments[1]['line'] == 11
    assert len(fake_client.comment_calls) == 0
    assert len(fake_client.thread_reply_calls) == 0
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_handles_reviewer_follow_up_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_reviewer_record('Vaquum_Agent1#25:pr_reviewer'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient(
        pull_request_files=_create_reviewer_pull_request_files(),
    )
    fake_codex = _FakeCodexExecutor(
        last_message=_create_reviewer_inline_payload('Reviewer summary B'),
    )
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_updated',
            details={'requires_follow_up': True},
            job_kind=JobKind.PR_REVIEWER,
            job_id='Vaquum_Agent1#25:pr_reviewer',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.review_submission_calls) == 1
    assert fake_client.review_submission_calls[0]['body'] == 'Reviewer summary B'
    assert fake_client.review_submission_calls[0]['event'] == 'COMMENT'
    review_comments = fake_client.review_submission_calls[0]['comments']
    assert isinstance(review_comments, list)
    assert len(review_comments) == 2
    assert len(fake_client.comment_calls) == 0
    assert len(fake_client.thread_reply_calls) == 0
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_routes_reviewer_thread_update_in_thread_only(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_reviewer_record('Vaquum_Agent1#25:pr_reviewer'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    fake_codex = _FakeCodexExecutor(last_message='thread reply body')
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_review_comment',
            details={
                'is_review_thread_comment': True,
                'review_comment_id': 4401,
                'thread_id': 'PRRC_kwDOAAABcd',
                'path': 'apps/backend/src/agent1/main.py',
                'line': 88,
                'side': 'RIGHT',
                'job_kind_hint': 'pr_reviewer',
            },
            job_kind=JobKind.PR_REVIEWER,
            job_id='Vaquum_Agent1#25:pr_reviewer',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.thread_reply_calls) == 1
    assert fake_client.thread_reply_calls[0]['body'] == 'thread reply body'
    assert len(fake_client.review_submission_calls) == 0
    assert len(fake_client.comment_calls) == 0
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_handles_author_review_comment_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_author_record('Vaquum_Agent1#25:pr_author'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_review_comment',
            details={
                'is_review_thread_comment': True,
                'review_comment_id': 4401,
                'thread_id': 'PRRC_kwDOAAABcd',
                'path': 'apps/backend/src/agent1/main.py',
                'line': 88,
                'side': 'RIGHT',
            },
            job_kind=JobKind.PR_AUTHOR,
            job_id='Vaquum_Agent1#25:pr_author',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.thread_reply_calls) == 1
    assert len(fake_client.comment_calls) == 0
    assert fake_client.thread_reply_calls[0]['body'] == 'Author follow-up Vaquum/Agent1#25  '
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_handles_author_ci_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_author_record('Vaquum_Agent1#25:pr_author'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_ci_failed',
            details={
                'check_name': 'integration-tests',
                'conclusion': 'failure',
            },
            job_kind=JobKind.PR_AUTHOR,
            job_id='Vaquum_Agent1#25:pr_author',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == (
        'Author follow-up Vaquum/Agent1#25 integration-tests failure'
    )
    assert updated.state == JobState.AWAITING_CI


def test_mention_action_executor_runs_codex_for_author_ci_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_author_record('Vaquum_Agent1#25:pr_author'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    fake_codex = _FakeCodexExecutor(status=ExecutionStatus.SUCCEEDED)
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_ci_failed',
            details={
                'check_name': 'integration-tests',
                'conclusion': 'failure',
            },
            job_kind=JobKind.PR_AUTHOR,
            job_id='Vaquum_Agent1#25:pr_author',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_codex.execute_calls) == 1
    assert fake_codex.execute_calls[0]['task_id'] == 'Vaquum_Agent1#25:pr_author:evt_mention_1:author_follow_up'
    assert 'IngressEvent: pr_ci_failed' in str(fake_codex.execute_calls[0]['prompt'])
    assert len(fake_client.comment_calls) == 1
    assert updated.state == JobState.AWAITING_CI


def test_mention_action_executor_passes_workspace_to_author_codex_execution(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_author_record('Vaquum_Agent1#25:pr_author'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    fake_codex = _FakeCodexExecutor(status=ExecutionStatus.SUCCEEDED)
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    workspace_path = '/tmp/agent1-repository-workspaces/Vaquum_Agent1'
    monkeypatch.setattr(
        executor,
        '_build_author_codex_prompt',
        lambda _normalized_event: 'author codex prompt',
    )
    monkeypatch.setattr(
        executor,
        '_resolve_author_codex_working_directory',
        lambda _normalized_event: workspace_path,
    )
    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_ci_failed',
            details={
                'check_name': 'integration-tests',
                'conclusion': 'failure',
            },
            job_kind=JobKind.PR_AUTHOR,
            job_id='Vaquum_Agent1#25:pr_author',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_codex.execute_calls) == 1
    assert fake_codex.execute_calls[0]['working_directory'] == workspace_path
    assert len(fake_client.comment_calls) == 1
    assert updated.state == JobState.AWAITING_CI


def test_resolve_author_codex_working_directory_prepares_clone_and_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    recorded_git_calls: list[tuple[list[str], str | None]] = []

    def _record_git_call(
        command: list[str],
        working_directory: object | None = None,
    ) -> bool:
        resolved_working_directory = None
        if working_directory is not None:
            resolved_working_directory = str(working_directory)
        recorded_git_calls.append((command, resolved_working_directory))
        return True

    monkeypatch.setattr(executor, '_run_git_command', _record_git_call)
    monkeypatch.setattr(
        'agent1.core.services.mention_action_executor.get_settings',
        lambda: SimpleNamespace(github_token='gho_test_token', github_user='bit-mis'),
    )
    monkeypatch.setattr(
        'agent1.core.services.mention_action_executor.CODEX_REPOSITORY_WORKSPACE_ROOT',
        str(tmp_path),
    )
    normalized_event = _create_normalized_event(
        'pr_ci_failed',
        details={
            'head_ref': 'fix/ci-remediation',
        },
        job_kind=JobKind.PR_AUTHOR,
        job_id='Vaquum_Agent1#25:pr_author',
    )

    resolved_working_directory = executor._resolve_author_codex_working_directory(normalized_event)

    expected_workspace_path = tmp_path / 'Vaquum_Agent1'
    assert resolved_working_directory == str(expected_workspace_path)
    assert len(recorded_git_calls) == 5
    assert recorded_git_calls[0][0][:2] == ['git', 'clone']
    assert recorded_git_calls[1][0] == ['git', 'fetch', 'origin', 'fix/ci-remediation']
    assert recorded_git_calls[2][0] == ['git', 'checkout', '-B', 'fix/ci-remediation', 'origin/fix/ci-remediation']
    assert recorded_git_calls[3][0] == ['git', 'config', 'user.name', 'bit-mis']


def test_mention_action_executor_blocks_when_codex_fails_for_author_ci_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_author_record('Vaquum_Agent1#25:pr_author'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    fake_codex = _FakeCodexExecutor(status=ExecutionStatus.FAILED)
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_ci_failed',
            details={
                'check_name': 'integration-tests',
                'conclusion': 'failure',
            },
            job_kind=JobKind.PR_AUTHOR,
            job_id='Vaquum_Agent1#25:pr_author',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        transition_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('action') == 'transition_job'
            and event.details.get('reason') == 'author_codex_execution_failed'
        ]

    assert len(fake_codex.execute_calls) == 1
    assert len(fake_client.comment_calls) == 0
    assert updated.state == JobState.BLOCKED
    assert len(transition_events) == 1
    transition_details = transition_events[0].details.get('transition_details')
    assert isinstance(transition_details, dict)
    assert transition_details.get('codex_summary') == 'codex execution'


def test_mention_action_executor_shadow_mode_skips_write_side_effects(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_record_with_mode('Vaquum_Agent1#25:issue_shadow', RuntimeMode.SHADOW),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event('issue_mention'),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 0
    assert len(fake_client.thread_reply_calls) == 0
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_shadow_mode_keeps_author_ci_no_write(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_record_with_mode(
            'Vaquum_Agent1#25:pr_author_shadow',
            RuntimeMode.SHADOW,
            kind=JobKind.PR_AUTHOR,
        ),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    fake_codex = _FakeCodexExecutor(status=ExecutionStatus.SUCCEEDED)
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_ci_failed',
            details={'check_name': 'integration-tests', 'conclusion': 'failure'},
            job_kind=JobKind.PR_AUTHOR,
            job_id='Vaquum_Agent1#25:pr_author_shadow',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 0
    assert len(fake_codex.execute_calls) == 0
    assert updated.state == JobState.AWAITING_CI


def test_mention_action_executor_skips_unsupported_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event('unsupported_event'),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 0
    assert updated.state == JobState.READY_TO_EXECUTE


def test_mention_action_executor_blocks_job_when_comment_fails(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient(should_fail=True)
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event('issue_mention'),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        transition_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('action') == 'transition_job'
            and event.details.get('reason') == 'mention_response_failed'
        ]

    assert len(fake_client.comment_calls) == 1
    assert updated.state == JobState.BLOCKED
    assert len(transition_events) == 1
    transition_details = transition_events[0].details.get('transition_details')
    assert isinstance(transition_details, dict)
    assert transition_details.get('error_message') == 'comment failure'
    assert transition_details.get('error_type') == 'RuntimeError'


def test_mention_action_executor_blocks_reviewer_job_with_error_details(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_reviewer_record('Vaquum_Agent1#25:pr_reviewer'),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient(
        should_fail=True,
        pull_request_files=_create_reviewer_pull_request_files(),
    )
    fake_codex = _FakeCodexExecutor(
        last_message=_create_reviewer_inline_payload('Reviewer summary C'),
    )
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
        codex_executor=fake_codex,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_review_requested',
            job_kind=JobKind.PR_REVIEWER,
            job_id='Vaquum_Agent1#25:pr_reviewer',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        transition_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('action') == 'transition_job'
            and event.details.get('reason') == 'reviewer_response_failed'
        ]

    assert updated.state == JobState.BLOCKED
    assert len(transition_events) == 1
    transition_details = transition_events[0].details.get('transition_details')
    assert isinstance(transition_details, dict)
    assert transition_details.get('error_message') == 'comment failure'
    assert transition_details.get('error_type') == 'RuntimeError'


def test_mention_action_executor_routes_review_thread_reply(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_review_comment',
            details={
                'is_review_thread_comment': True,
                'review_comment_id': 4401,
                'thread_id': 'PRRC_kwDOAAABcd',
                'path': 'apps/backend/src/agent1/main.py',
                'line': 88,
                'side': 'RIGHT',
            },
        ),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        comment_targets = verification_session.query(CommentTargetModel).all()

    assert len(fake_client.thread_reply_calls) == 1
    assert len(fake_client.comment_calls) == 0
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK
    assert len(comment_targets) == 1
    assert comment_targets[0].target_type == CommentTargetType.PR_REVIEW_THREAD
    assert comment_targets[0].review_comment_id == 4401
    assert comment_targets[0].target_identity == 'Vaquum/Agent1:pr:25:thread:PRRC_kwDOAAABcd:4401'


def test_mention_action_executor_blocks_on_missing_review_thread_metadata(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        require_review_thread_reply=True,
        allow_top_level_pr_fallback=False,
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'pr_review_comment',
            details={
                'is_review_thread_comment': True,
                'review_comment_id': 4401,
            },
        ),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        alert_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('alert_name') == COMMENT_ROUTING_FAILURES_ALERT
        ]

    assert len(fake_client.thread_reply_calls) == 0
    assert len(fake_client.comment_calls) == 0
    assert updated.state == JobState.BLOCKED
    assert len(alert_events) == 1
    assert alert_events[0].details['runbook'] == 'docs/Developer/runbooks/review-thread-routing-failures.md'


def test_mention_action_executor_posts_clarification_for_insufficient_assignment(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_record_with_state('Vaquum_Agent1#25:issue', JobState.AWAITING_CONTEXT),
        trace_id='trc_create',
    )
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'issue_assignment',
            details={
                'has_sufficient_context': False,
            },
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'Need clarification for Vaquum/Agent1#25'
    assert updated.state == JobState.BLOCKED


def test_mention_action_executor_executes_direct_assignment_with_sufficient_context(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    fake_client = _FakeGitHubClient(
        issue_payload={'body': 'Respond "hello world" if you see this message.'},
    )
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event(
            'issue_assignment',
            details={
                'has_sufficient_context': True,
            },
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'hello world'
    assert updated.state == JobState.COMPLETED


def test_mention_action_executor_rejects_stale_lease_mutating_write(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(_create_record('Vaquum_Agent1#25:issue'), trace_id='trc_create')
    orchestrator.claim_job(created.job_id, trace_id='trc_claim')
    fake_client = _FakeGitHubClient()
    executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )

    updated = executor.execute_for_event(
        normalized_event=_create_normalized_event('issue_mention'),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        alert_events = [
            event
            for event in verification_session.query(EventJournalModel).all()
            if event.details.get('alert_name') == LEASE_VIOLATIONS_ALERT
        ]

    assert len(fake_client.comment_calls) == 0
    assert updated.lease_epoch == 1
    assert updated.state == JobState.READY_TO_EXECUTE
    assert len(alert_events) == 1
