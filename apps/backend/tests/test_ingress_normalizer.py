from __future__ import annotations

from datetime import datetime
from datetime import timezone

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEntityType
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_normalizer import GitHubIngressNormalizer


def test_issue_assignment_without_context_normalizes_to_awaiting_context() -> None:
    normalizer = GitHubIngressNormalizer(environment=EnvironmentName.DEV)
    ingress_event = GitHubIngressEvent(
        event_id='evt_issue_assign_1',
        repository='Vaquum/Agent1',
        entity_number=12,
        entity_type=IngressEntityType.ISSUE,
        actor='mikkokotila',
        event_type=IngressEventType.ISSUE_ASSIGNMENT,
        timestamp=datetime.now(timezone.utc),
        details={'has_sufficient_context': False},
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is not None
    assert normalized.job_kind == JobKind.ISSUE
    assert normalized.initial_state == JobState.AWAITING_CONTEXT
    assert normalized.transition_to is None


def test_pr_review_request_normalizes_to_reviewer_kind() -> None:
    normalizer = GitHubIngressNormalizer(environment=EnvironmentName.DEV)
    ingress_event = GitHubIngressEvent(
        event_id='evt_pr_review_1',
        repository='Vaquum/Agent1',
        entity_number=33,
        entity_type=IngressEntityType.PR,
        actor='mikkokotila',
        event_type=IngressEventType.PR_REVIEW_REQUESTED,
        timestamp=datetime.now(timezone.utc),
        details={},
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is not None
    assert normalized.job_kind == JobKind.PR_REVIEWER
    assert normalized.initial_state == JobState.READY_TO_EXECUTE


def test_issue_updated_with_context_transitions_to_ready_to_execute() -> None:
    normalizer = GitHubIngressNormalizer(environment=EnvironmentName.DEV)
    ingress_event = GitHubIngressEvent(
        event_id='evt_issue_updated_1',
        repository='Vaquum/Agent1',
        entity_number=14,
        entity_type=IngressEntityType.ISSUE,
        actor='mikkokotila',
        event_type=IngressEventType.ISSUE_UPDATED,
        timestamp=datetime.now(timezone.utc),
        details={'has_sufficient_context': True},
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is not None
    assert normalized.job_kind == JobKind.ISSUE
    assert normalized.transition_to == JobState.READY_TO_EXECUTE
    assert normalized.transition_reason == 'issue_updated_context_refresh'


def test_pr_updated_with_human_terminal_decision_transitions_to_completed() -> None:
    normalizer = GitHubIngressNormalizer(environment=EnvironmentName.DEV)
    ingress_event = GitHubIngressEvent(
        event_id='evt_pr_terminal_decision_1',
        repository='Vaquum/Agent1',
        entity_number=15,
        entity_type=IngressEntityType.PR,
        actor='mikkokotila',
        event_type=IngressEventType.PR_UPDATED,
        timestamp=datetime.now(timezone.utc),
        details={
            'human_terminal_decision': 'closed',
        },
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is not None
    assert normalized.job_kind == JobKind.PR_AUTHOR
    assert normalized.transition_to == JobState.COMPLETED
    assert normalized.transition_reason == 'pr_human_terminal_decision_closed'


def test_issue_mention_from_agent_actor_is_ignored() -> None:
    normalizer = GitHubIngressNormalizer(
        environment=EnvironmentName.DEV,
        agent_actor='zero-bang',
    )
    ingress_event = GitHubIngressEvent(
        event_id='evt_issue_self_mention_1',
        repository='Vaquum/Agent1',
        entity_number=16,
        entity_type=IngressEntityType.ISSUE,
        actor='zero-bang',
        event_type=IngressEventType.ISSUE_MENTION,
        timestamp=datetime.now(timezone.utc),
        details={},
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is None


def test_review_comment_from_bot_actor_is_ignored() -> None:
    normalizer = GitHubIngressNormalizer(environment=EnvironmentName.DEV)
    ingress_event = GitHubIngressEvent(
        event_id='evt_pr_bot_review_comment_1',
        repository='Vaquum/Agent1',
        entity_number=17,
        entity_type=IngressEntityType.PR,
        actor='copilot[bot]',
        event_type=IngressEventType.PR_REVIEW_COMMENT,
        timestamp=datetime.now(timezone.utc),
        details={},
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is None


def test_ci_failure_from_bot_actor_remains_actionable() -> None:
    normalizer = GitHubIngressNormalizer(environment=EnvironmentName.DEV)
    ingress_event = GitHubIngressEvent(
        event_id='evt_pr_bot_ci_failed_1',
        repository='Vaquum/Agent1',
        entity_number=18,
        entity_type=IngressEntityType.PR,
        actor='github-actions[bot]',
        event_type=IngressEventType.PR_CI_FAILED,
        timestamp=datetime.now(timezone.utc),
        details={},
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is not None
    assert normalized.transition_to == JobState.READY_TO_EXECUTE
    assert normalized.transition_reason == IngressEventType.PR_CI_FAILED.value


def test_normalizer_filters_repository_out_of_scope() -> None:
    normalizer = GitHubIngressNormalizer(
        environment=EnvironmentName.DEV,
        runtime_mode=RuntimeMode.ACTIVE,
        active_repositories=['Vaquum/Agent1'],
    )
    ingress_event = GitHubIngressEvent(
        event_id='evt_out_of_scope_1',
        repository='Vaquum/Other',
        entity_number=19,
        entity_type=IngressEntityType.ISSUE,
        actor='mikkokotila',
        event_type=IngressEventType.ISSUE_MENTION,
        timestamp=datetime.now(timezone.utc),
        details={},
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is None


def test_normalizer_filters_dev_active_non_sandbox_scope() -> None:
    normalizer = GitHubIngressNormalizer(
        environment=EnvironmentName.DEV,
        runtime_mode=RuntimeMode.ACTIVE,
        active_repositories=['Vaquum/Agent1'],
        require_sandbox_scope_for_dev_active=True,
        sandbox_label='agent1-sandbox',
        sandbox_branch_prefix='sandbox/',
    )
    ingress_event = GitHubIngressEvent(
        event_id='evt_non_sandbox_1',
        repository='Vaquum/Agent1',
        entity_number=20,
        entity_type=IngressEntityType.PR,
        actor='mikkokotila',
        event_type=IngressEventType.PR_MENTION,
        timestamp=datetime.now(timezone.utc),
        details={
            'label_names': ['priority:high'],
            'head_ref': 'feature/new-flow',
        },
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is None


def test_normalizer_accepts_dev_active_sandbox_scope() -> None:
    normalizer = GitHubIngressNormalizer(
        environment=EnvironmentName.DEV,
        runtime_mode=RuntimeMode.ACTIVE,
        active_repositories=['Vaquum/Agent1'],
        require_sandbox_scope_for_dev_active=True,
        sandbox_label='agent1-sandbox',
        sandbox_branch_prefix='sandbox/',
    )
    ingress_event = GitHubIngressEvent(
        event_id='evt_sandbox_1',
        repository='Vaquum/Agent1',
        entity_number=21,
        entity_type=IngressEntityType.PR,
        actor='mikkokotila',
        event_type=IngressEventType.PR_MENTION,
        timestamp=datetime.now(timezone.utc),
        details={
            'label_names': ['agent1-sandbox'],
            'head_ref': 'sandbox/ci-fix',
        },
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is not None
    assert normalized.entity_key == 'Vaquum/Agent1#21'


def test_normalizer_filters_prod_active_sandbox_scope() -> None:
    normalizer = GitHubIngressNormalizer(
        environment=EnvironmentName.PROD,
        runtime_mode=RuntimeMode.ACTIVE,
        active_repositories=['Vaquum/Agent1'],
        require_sandbox_scope_for_dev_active=True,
        sandbox_label='agent1-sandbox',
        sandbox_branch_prefix='sandbox/',
    )
    ingress_event = GitHubIngressEvent(
        event_id='evt_prod_sandbox_filtered_1',
        repository='Vaquum/Agent1',
        entity_number=22,
        entity_type=IngressEntityType.PR,
        actor='mikkokotila',
        event_type=IngressEventType.PR_MENTION,
        timestamp=datetime.now(timezone.utc),
        details={
            'label_names': ['agent1-sandbox'],
            'head_ref': 'sandbox/isolation-check',
        },
    )

    normalized = normalizer.normalize_event(ingress_event)

    assert normalized is None
