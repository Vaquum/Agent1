from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from agent1.adapters.github.scanner import InMemoryGitHubIngressScanner
from agent1.adapters.github.scanner import GitHubNotificationScanner
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
        self.comment_count += 1
        return {'repository': repository, 'issue_number': issue_number, 'body': body}

    def post_pull_review_comment_reply(
        self,
        repository: str,
        pull_number: int,
        review_comment_id: int,
        body: str,
    ) -> dict[str, object]:
        self.comment_count += 1
        return {
            'repository': repository,
            'pull_number': pull_number,
            'review_comment_id': review_comment_id,
            'body': body,
        }


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
    mention_executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )
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
    mention_executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )
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
    mention_executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )
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
                actor='zero-bang',
                event_type=IngressEventType.ISSUE_MENTION,
                timestamp=datetime.now(timezone.utc),
                details={},
            )
        ]
    )
    persistence_service = PersistenceService(session_factory=session_factory)
    orchestrator = JobOrchestrator(persistence_service=persistence_service)
    fake_client = _FakeMentionGitHubClient()
    mention_executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )
    normalizer = GitHubIngressNormalizer(agent_actor='zero-bang')
    coordinator = GitHubIngressCoordinator(
        scanner=scanner,
        orchestrator=orchestrator,
        normalizer=normalizer,
        mention_executor=mention_executor,
    )

    processed_jobs = coordinator.process_once()

    assert len(processed_jobs) == 0
    assert fake_client.comment_count == 0


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
    mention_executor = MentionActionExecutor(
        response_template='Ack {entity_key}',
        clarification_template='Need clarification for {entity_key}',
        reviewer_follow_up_template='Reviewer follow-up {entity_key}',
        author_follow_up_template='Author follow-up {entity_key} {check_name} {conclusion}',
        github_client=fake_client,
    )
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
