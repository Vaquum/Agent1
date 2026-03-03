from __future__ import annotations

from datetime import datetime
from datetime import timezone

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


class _FakeGitHubClient:
    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail
        self.comment_calls: list[dict[str, object]] = []
        self.thread_reply_calls: list[dict[str, object]] = []

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
        return {}

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:
        return {}

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


class _FakeCodexExecutor:
    def __init__(self, status: ExecutionStatus = ExecutionStatus.SUCCEEDED) -> None:
        self._status = status
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
            metadata={},
        )


def test_mention_action_executor_posts_comment_and_advances_state(
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
        normalized_event=_create_normalized_event('issue_mention'),
        current_job=created,
        orchestrator=orchestrator,
    )
    with session_factory() as verification_session:
        comment_targets = verification_session.query(CommentTargetModel).all()
        outbox_entries = verification_session.query(OutboxEntryModel).all()

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'Ack Vaquum/Agent1#25'
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK
    assert len(comment_targets) == 1
    assert comment_targets[0].target_type == CommentTargetType.ISSUE
    assert len(outbox_entries) == 1
    assert outbox_entries[0].status == OutboxStatus.CONFIRMED


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
    assert updated.state == JobState.AWAITING_HUMAN_FEEDBACK


def test_mention_action_executor_handles_reviewer_request_event(
    session_factory: sessionmaker[Session],
) -> None:
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    created = orchestrator.create_job(
        _create_reviewer_record('Vaquum_Agent1#25:pr_reviewer'),
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
            'pr_review_requested',
            job_kind=JobKind.PR_REVIEWER,
            job_id='Vaquum_Agent1#25:pr_reviewer',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'Reviewer follow-up Vaquum/Agent1#25'
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
            'pr_updated',
            details={'requires_follow_up': True},
            job_kind=JobKind.PR_REVIEWER,
            job_id='Vaquum_Agent1#25:pr_reviewer',
        ),
        current_job=created,
        orchestrator=orchestrator,
    )

    assert len(fake_client.comment_calls) == 1
    assert fake_client.comment_calls[0]['body'] == 'Reviewer follow-up Vaquum/Agent1#25'
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

    assert len(fake_codex.execute_calls) == 1
    assert len(fake_client.comment_calls) == 0
    assert updated.state == JobState.BLOCKED


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


def test_mention_action_executor_skips_non_mention_event(
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
        normalized_event=_create_normalized_event('issue_assignment'),
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

    assert len(fake_client.comment_calls) == 1
    assert updated.state == JobState.BLOCKED


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
