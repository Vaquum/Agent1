from __future__ import annotations

from datetime import datetime
from datetime import timezone
import json

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.adapters.github.scanner import InMemoryGitHubIngressScanner
from agent1.adapters.github.scanner import GitHubNotificationScanner
from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import EntityType
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.contracts import RuntimeMode
from agent1.core.contracts import JobState
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_coordinator import GitHubIngressCoordinator
from agent1.core.ingress_coordinator import GITHUB_NOTIFICATION_CURSOR_KEY
from agent1.core.ingress_coordinator import create_runtime_ingress_coordinator
from agent1.core.ingress_normalizer import GitHubIngressNormalizer
from agent1.core.orchestrator import JobOrchestrator
from agent1.core.services.ingress_cursor_store import PersistenceIngressCursorStore
from agent1.core.services.mention_action_executor import MentionActionExecutor
from agent1.core.services.persistence_service import PersistenceService
from agent1.db.models import GitHubEventModel
from agent1.db.models import JobTransitionModel


def test_ingress_coordinator_creates_and_advances_issue_job(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_1',
                repository='Vaquum/Agent1',
                entity_number=50,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_ASSIGNMENT,
                timestamp=datetime.now(timezone.utc),
                details={'has_sufficient_context': False},
            ),
            GitHubIngressEvent(
                event_id='evt_2',
                repository='Vaquum/Agent1',
                entity_number=50,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime.now(timezone.utc),
                details={},
            ),
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 2
    assert processed_jobs[-1].state == JobState.READY_TO_EXECUTE


def test_ingress_coordinator_persists_entity_for_normalized_event(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_entity_persist_1',
                repository='Vaquum/Agent1',
                entity_number=55,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime.now(timezone.utc),
                details={'label_names': ['agent1-sandbox']},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
    )

    processed_jobs = coordinator.process_once()
    persisted_entity = persistence_service.get_entity(
        environment=processed_jobs[0].environment,
        entity_key='Vaquum/Agent1#55',
    )

    assert len(processed_jobs) == 1
    assert persisted_entity is not None
    assert persisted_entity.entity_type == EntityType.ISSUE
    assert persisted_entity.is_sandbox is True


def test_runtime_ingress_coordinator_uses_persistent_cursor_store() -> None:
    coordinator = create_runtime_ingress_coordinator()
    scanner = coordinator.get_scanner()

    assert isinstance(scanner, GitHubNotificationScanner)
    assert isinstance(scanner.get_cursor_store(), PersistenceIngressCursorStore)
    assert scanner.get_cursor_key() == GITHUB_NOTIFICATION_CURSOR_KEY


def test_ingress_coordinator_creates_jobs_with_runtime_mode(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_runtime_mode_1',
                repository='Vaquum/Agent1',
                entity_number=96,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime.now(timezone.utc),
                details={},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        runtime_mode=RuntimeMode.SHADOW,
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 1
    assert processed_jobs[0].mode == RuntimeMode.SHADOW


class _FakeMentionGitHubClient:
    def __init__(self) -> None:
        self.comment_count = 0
        self.issue_comment_numbers: list[int] = []
        self.review_reply_comment_ids: list[int] = []
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
        return {}

    def fetch_pull_request(
        self,
        repository: str,
        pull_number: int,
    ) -> dict[str, object]:
        return {}

    def fetch_pull_request_files(
        self,
        repository: str,
        pull_number: int,
    ) -> list[dict[str, object]]:
        _ = repository
        _ = pull_number
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

    def post_issue_comment(
        self,
        repository: str,
        issue_number: int,
        body: str,
    ) -> dict[str, object]:
        self.comment_count += 1
        self.issue_comment_numbers.append(issue_number)
        return {'repository': repository, 'issue_number': issue_number, 'body': body}

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        self.comment_count += 1
        self.review_reply_comment_ids.append(review_comment_id)
        return {
            'repository': repository,
            'pull_number': pull_number,
            'review_comment_id': review_comment_id,
            'body': body,
        }

    def submit_pull_request_review(
        self,
        repository: str,
        pull_number: int,
        body: str,
        event: str = 'COMMENT',
        comments: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        self.comment_count += 1
        self.review_submission_calls.append(
            {
                'repository': repository,
                'pull_number': pull_number,
                'body': body,
                'event': event,
                'comments': comments,
            }
        )
        return {
            'repository': repository,
            'pull_number': pull_number,
            'body': body,
            'event': event,
            'comments': comments,
        }


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


class _FakeMentionCodexExecutor:
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
        response_message = self._last_message
        if task_id.endswith('reviewer_follow_up'):
            response_message = _create_reviewer_inline_payload('Reviewer summary')
        return ExecutionResult(
            status=self._status,
            summary='codex execution',
            command='codex exec',
            exit_code=0 if self._status == ExecutionStatus.SUCCEEDED else 1,
            metadata={'last_message': response_message},
        )


def _create_mention_executor(
    github_client: _FakeMentionGitHubClient,
    codex_executor: _FakeMentionCodexExecutor | None = None,
) -> MentionActionExecutor:
    resolved_codex_executor = codex_executor
    if resolved_codex_executor is None:
        resolved_codex_executor = _FakeMentionCodexExecutor()

    return MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        issue_mention_codex_prompt_template='Issue mention prompt for {entity_key}',
        pr_mention_codex_prompt_template='PR mention prompt for {entity_key}',
        issue_assignment_codex_prompt_template='Issue assignment prompt for {entity_key}',
        reviewer_codex_review_prompt_template='Reviewer review prompt for {entity_key}',
        reviewer_codex_thread_reply_prompt_template='Reviewer thread reply prompt for {entity_key}',
        author_codex_prompt_template='Author follow-up prompt for {entity_key} {check_name} {conclusion}',
        github_client=github_client,
        codex_executor=resolved_codex_executor,
    )


def test_ingress_coordinator_executes_mention_side_effect(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_mention_side_effect',
                repository='Vaquum/Agent1',
                entity_number=88,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime.now(timezone.utc),
                details={},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert fake_client.comment_count == 1
    assert len(processed_jobs) == 1
    assert processed_jobs[0].state == JobState.AWAITING_HUMAN_FEEDBACK


def test_ingress_coordinator_executes_pr_mention_side_effect(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_pr_mention_side_effect',
                repository='Vaquum/Agent1',
                entity_number=89,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_MENTION,
                timestamp=datetime.now(timezone.utc),
                details={},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert fake_client.comment_count == 1
    assert len(processed_jobs) == 1
    assert processed_jobs[0].state == JobState.AWAITING_HUMAN_FEEDBACK


def test_ingress_coordinator_resumes_blocked_assignment_on_issue_update(
    session_factory: sessionmaker[Session],
) -> None:
    assignment_scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_assignment_clarify_1',
                repository='Vaquum/Agent1',
                entity_number=77,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_ASSIGNMENT,
                timestamp=datetime.now(timezone.utc),
                details={'has_sufficient_context': False},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    first_coordinator = GitHubIngressCoordinator(
        scanner=assignment_scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    first_jobs = first_coordinator.process_once()

    update_scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_issue_update_resume_1',
                repository='Vaquum/Agent1',
                entity_number=77,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_UPDATED,
                timestamp=datetime.now(timezone.utc),
                details={'has_sufficient_context': True},
            )
        ]
    )
    second_coordinator = GitHubIngressCoordinator(
        scanner=update_scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    second_jobs = second_coordinator.process_once()

    assert len(first_jobs) == 1
    assert first_jobs[0].state == JobState.BLOCKED
    assert len(second_jobs) == 1
    assert second_jobs[0].state == JobState.AWAITING_HUMAN_FEEDBACK
    assert fake_client.comment_count == 2


def test_ingress_coordinator_executes_direct_assignment_with_sufficient_context(
    session_factory: sessionmaker[Session],
) -> None:
    assignment_scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_assignment_direct_1',
                repository='Vaquum/Agent1',
                entity_number=78,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_ASSIGNMENT,
                timestamp=datetime.now(timezone.utc),
                details={'has_sufficient_context': True},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=assignment_scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 1
    assert processed_jobs[0].state == JobState.AWAITING_HUMAN_FEEDBACK
    assert fake_client.comment_count == 1


def test_ingress_coordinator_reviewer_cycle_handles_follow_up_updates(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_review_requested_1',
                repository='Vaquum/Agent1',
                entity_number=91,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_REVIEW_REQUESTED,
                timestamp=datetime.now(timezone.utc),
                details={},
            ),
            GitHubIngressEvent(
                event_id='evt_review_follow_up_1',
                repository='Vaquum/Agent1',
                entity_number=91,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_UPDATED,
                timestamp=datetime.now(timezone.utc),
                details={
                    'job_kind_hint': 'pr_reviewer',
                    'requires_follow_up': True,
                },
            ),
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 2
    assert fake_client.comment_count == 2
    assert processed_jobs[-1].state == JobState.AWAITING_HUMAN_FEEDBACK


def test_ingress_coordinator_handles_multi_round_lifecycle_until_human_terminal_decision(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_multi_round_review_requested_1',
                repository='Vaquum/Agent1',
                entity_number=92,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_REVIEW_REQUESTED,
                timestamp=datetime.now(timezone.utc),
                details={},
            ),
            GitHubIngressEvent(
                event_id='evt_multi_round_follow_up_1',
                repository='Vaquum/Agent1',
                entity_number=92,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_UPDATED,
                timestamp=datetime.now(timezone.utc),
                details={
                    'job_kind_hint': 'pr_reviewer',
                    'requires_follow_up': True,
                },
            ),
            GitHubIngressEvent(
                event_id='evt_multi_round_follow_up_2',
                repository='Vaquum/Agent1',
                entity_number=92,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_UPDATED,
                timestamp=datetime.now(timezone.utc),
                details={
                    'job_kind_hint': 'pr_reviewer',
                    'requires_follow_up': True,
                },
            ),
            GitHubIngressEvent(
                event_id='evt_multi_round_terminal_decision_1',
                repository='Vaquum/Agent1',
                entity_number=92,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_UPDATED,
                timestamp=datetime.now(timezone.utc),
                details={
                    'job_kind_hint': 'pr_reviewer',
                    'requires_follow_up': False,
                    'human_terminal_decision': 'closed',
                },
            ),
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    with session_factory() as verification_session:
        transitions = (
            verification_session.query(JobTransitionModel)
            .filter(JobTransitionModel.job_id == processed_jobs[0].job_id)
            .order_by(JobTransitionModel.id.asc())
            .all()
        )

    assert len(processed_jobs) == 4
    assert fake_client.comment_count == 3
    assert [job.state for job in processed_jobs] == [
        JobState.AWAITING_HUMAN_FEEDBACK,
        JobState.AWAITING_HUMAN_FEEDBACK,
        JobState.AWAITING_HUMAN_FEEDBACK,
        JobState.COMPLETED,
    ]
    assert [transition.reason for transition in transitions] == [
        'reviewer_action_started',
        'reviewer_response_posted',
        'pr_updated_requires_follow_up',
        'reviewer_action_started',
        'reviewer_response_posted',
        'pr_updated_requires_follow_up',
        'reviewer_action_started',
        'reviewer_response_posted',
        'pr_human_terminal_decision_closed',
    ]


def test_ingress_coordinator_ignores_self_triggered_mentions(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_self_mention_1',
                repository='Vaquum/Agent1',
                entity_number=93,
                entity_type=IngressEntityType.ISSUE,
                actor='runtime-agent-user',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime.now(timezone.utc),
                details={},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    normalizer = GitHubIngressNormalizer(agent_actor='runtime-agent-user')
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=normalizer,
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 0
    assert fake_client.comment_count == 0


def test_ingress_coordinator_scoped_dev_prod_harness_avoids_duplicate_side_effects(
    session_factory: sessionmaker[Session],
) -> None:
    ingress_events = [
        GitHubIngressEvent(
            event_id='evt_dev_prod_isolation_sandbox_1',
            repository='Vaquum/Agent1',
            entity_number=120,
            entity_type=IngressEntityType.ISSUE,
            actor='mikkokotila',
            event_type=IngressEventType.ISSUE_MENTION,
            timestamp=datetime.now(timezone.utc),
            details={'label_names': ['agent1-sandbox']},
        ),
        GitHubIngressEvent(
            event_id='evt_dev_prod_isolation_prod_1',
            repository='Vaquum/Agent1',
            entity_number=121,
            entity_type=IngressEntityType.ISSUE,
            actor='mikkokotila',
            event_type=IngressEventType.ISSUE_MENTION,
            timestamp=datetime.now(timezone.utc),
            details={'label_names': ['priority:high']},
        ),
    ]
    dev_scanner = InMemoryGitHubIngressScanner(ingress_events)
    prod_scanner = InMemoryGitHubIngressScanner(ingress_events)

    dev_persistence_service = PersistenceService(session_factory=session_factory)
    prod_persistence_service = PersistenceService(session_factory=session_factory)
    dev_orchestrator = JobOrchestrator(persistence_service=dev_persistence_service)
    prod_orchestrator = JobOrchestrator(persistence_service=prod_persistence_service)

    dev_client = _FakeMentionGitHubClient()
    prod_client = _FakeMentionGitHubClient()
    dev_executor = _create_mention_executor(github_client=dev_client)
    prod_executor = _create_mention_executor(github_client=prod_client)

    dev_normalizer = GitHubIngressNormalizer(
        environment=EnvironmentName.DEV,
        runtime_mode=RuntimeMode.ACTIVE,
        active_repositories=['Vaquum/Agent1'],
        require_sandbox_scope_for_dev_active=True,
        sandbox_label='agent1-sandbox',
        sandbox_branch_prefix='sandbox/',
    )
    prod_normalizer = GitHubIngressNormalizer(
        environment=EnvironmentName.PROD,
        runtime_mode=RuntimeMode.ACTIVE,
        active_repositories=['Vaquum/Agent1'],
        require_sandbox_scope_for_dev_active=True,
        sandbox_label='agent1-sandbox',
        sandbox_branch_prefix='sandbox/',
    )
    dev_coordinator = GitHubIngressCoordinator(
        scanner=dev_scanner,
        orchestrator=dev_orchestrator,
        normalizer=dev_normalizer,
        mention_executor=dev_executor,
        runtime_mode=RuntimeMode.ACTIVE,
        environment=EnvironmentName.DEV,
    )
    prod_coordinator = GitHubIngressCoordinator(
        scanner=prod_scanner,
        orchestrator=prod_orchestrator,
        normalizer=prod_normalizer,
        mention_executor=prod_executor,
        runtime_mode=RuntimeMode.ACTIVE,
        environment=EnvironmentName.PROD,
    )

    dev_jobs = dev_coordinator.process_once()
    prod_jobs = prod_coordinator.process_once()

    assert len(dev_jobs) == 1
    assert len(prod_jobs) == 1
    assert dev_client.comment_count == 1
    assert prod_client.comment_count == 1
    assert dev_client.issue_comment_numbers == [120]
    assert prod_client.issue_comment_numbers == [121]
    assert dev_jobs[0].state == JobState.AWAITING_HUMAN_FEEDBACK
    assert prod_jobs[0].state == JobState.AWAITING_HUMAN_FEEDBACK
    assert dev_jobs[0].environment == EnvironmentName.DEV
    assert prod_jobs[0].environment == EnvironmentName.PROD


def test_ingress_coordinator_handles_pr_author_ci_cycle(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_pr_ci_failed_1',
                repository='Vaquum/Agent1',
                entity_number=94,
                entity_type=IngressEntityType.PR,
                actor='github-actions',
                event_type=IngressEventType.PR_CI_FAILED,
                timestamp=datetime.now(timezone.utc),
                details={
                    'check_name': 'integration-tests',
                    'conclusion': 'failure',
                },
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 1
    assert fake_client.comment_count == 1
    assert processed_jobs[0].state == JobState.AWAITING_CI


def test_ingress_coordinator_handles_pr_author_change_request_follow_up(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_pr_change_request_1',
                repository='Vaquum/Agent1',
                entity_number=95,
                entity_type=IngressEntityType.PR,
                actor='mikkokotila',
                event_type=IngressEventType.PR_REVIEW_COMMENT,
                timestamp=datetime.now(timezone.utc),
                details={
                    'is_review_thread_comment': False,
                    'job_kind_hint': 'pr_author',
                },
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 1
    assert fake_client.comment_count == 1
    assert processed_jobs[0].state == JobState.AWAITING_HUMAN_FEEDBACK


def test_ingress_coordinator_persists_stale_events_and_skips_processing(
    session_factory: sessionmaker[Session],
) -> None:
    scanner = InMemoryGitHubIngressScanner(
        [
            GitHubIngressEvent(
                event_id='evt_ordering_newer',
                repository='Vaquum/Agent1',
                entity_number=97,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime(2026, 3, 5, 10, 1, tzinfo=timezone.utc),
                details={},
            ),
            GitHubIngressEvent(
                event_id='evt_ordering_older',
                repository='Vaquum/Agent1',
                entity_number=97,
                entity_type=IngressEntityType.ISSUE,
                actor='mikkokotila',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
                details={},
            ),
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = _create_mention_executor(github_client=fake_client)
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=GitHubIngressNormalizer(),
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    with session_factory() as verification_session:
        ingress_event_count = verification_session.query(GitHubEventModel).count()
        stale_event_count = (
            verification_session.query(GitHubEventModel)
            .filter(GitHubEventModel.is_stale.is_(True))
            .count()
        )

    assert len(processed_jobs) == 1
    assert fake_client.comment_count == 1
    assert ingress_event_count == 2
    assert stale_event_count == 1
