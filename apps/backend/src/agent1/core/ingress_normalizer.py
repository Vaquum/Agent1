from __future__ import annotations

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_contracts import GitHubIngressEvent
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import NormalizedIngressEvent


IGNORED_ACTOR_EVENT_TYPES = frozenset(
    {
        IngressEventType.ISSUE_MENTION,
        IngressEventType.ISSUE_UPDATED,
        IngressEventType.PR_MENTION,
        IngressEventType.PR_REVIEW_COMMENT,
    }
)
DEFAULT_IGNORED_ACTOR_SUFFIXES = ('[bot]',)


def _normalize_active_repositories(active_repositories: list[str] | None) -> set[str]:

    '''
    Create normalized active-repository scope set for ingress filtering.

    Args:
    active_repositories (list[str] | None): Raw repository scope values.

    Returns:
    set[str]: Normalized repository scope set.
    '''

    return {
        repository.strip()
        for repository in (active_repositories or [])
        if repository.strip() != ''
    }


class GitHubIngressNormalizer:
    def __init__(
        self,
        environment: EnvironmentName = EnvironmentName.DEV,
        runtime_mode: RuntimeMode = RuntimeMode.ACTIVE,
        active_repositories: list[str] | None = None,
        require_sandbox_scope_for_dev_active: bool = False,
        sandbox_label: str = 'agent1-sandbox',
        sandbox_branch_prefix: str = 'sandbox/',
        agent_actor: str = '',
        ignored_actors: list[str] | None = None,
        ignored_actor_suffixes: list[str] | None = None,
    ) -> None:
        self._environment = environment
        self._runtime_mode = runtime_mode
        self._active_repositories = _normalize_active_repositories(active_repositories)
        self._require_sandbox_scope_for_dev_active = require_sandbox_scope_for_dev_active
        self._sandbox_label = sandbox_label.strip()
        self._sandbox_branch_prefix = sandbox_branch_prefix.strip()
        self._agent_actor = agent_actor.strip().lower()
        self._ignored_actors = {
            actor.strip().lower()
            for actor in (ignored_actors or [])
            if actor.strip() != ''
        }
        self._ignored_actor_suffixes = tuple(
            suffix.strip().lower()
            for suffix in (
                ignored_actor_suffixes
                if ignored_actor_suffixes is not None
                else DEFAULT_IGNORED_ACTOR_SUFFIXES
            )
            if suffix.strip() != ''
        )

    def set_active_repositories(self, active_repositories: list[str]) -> None:

        '''
        Create runtime active-repository scope update for ingress filtering.

        Args:
        active_repositories (list[str]): Runtime active repository scope list.
        '''

        self._active_repositories = _normalize_active_repositories(active_repositories)

    def get_active_repositories(self) -> list[str]:

        '''
        Create sorted runtime active-repository scope list for diagnostics.

        Returns:
        list[str]: Sorted runtime active repository scope list.
        '''

        return sorted(self._active_repositories)

    def _is_ignored_actor_event(self, ingress_event: GitHubIngressEvent) -> bool:
        if ingress_event.event_type not in IGNORED_ACTOR_EVENT_TYPES:
            return False

        actor = ingress_event.actor.strip().lower()
        if actor == '':
            return False

        if actor == self._agent_actor:
            return True

        if actor in self._ignored_actors:
            return True

        return any(actor.endswith(suffix) for suffix in self._ignored_actor_suffixes)

    def _is_sandbox_scope_event(self, ingress_event: GitHubIngressEvent) -> bool:
        labels_value = ingress_event.details.get('label_names')
        labels: set[str] = set()
        if isinstance(labels_value, list):
            labels = {
                label.strip()
                for label in labels_value
                if isinstance(label, str) and label.strip() != ''
            }

        if self._sandbox_label in labels:
            return True

        if ingress_event.entity_type.value != 'pr':
            return False

        head_ref = ingress_event.details.get('head_ref')
        if not isinstance(head_ref, str):
            return False

        return (
            self._sandbox_branch_prefix != ''
            and head_ref.strip().startswith(self._sandbox_branch_prefix)
        )

    def _is_out_of_scope_event(self, ingress_event: GitHubIngressEvent) -> bool:
        if len(self._active_repositories) > 0 and ingress_event.repository not in self._active_repositories:
            return True

        if (
            self._runtime_mode == RuntimeMode.ACTIVE
            and self._environment == EnvironmentName.PROD
            and self._is_sandbox_scope_event(ingress_event)
        ):
            return True

        if (
            self._runtime_mode == RuntimeMode.ACTIVE
            and self._environment == EnvironmentName.DEV
            and self._require_sandbox_scope_for_dev_active
            and self._is_sandbox_scope_event(ingress_event) is False
        ):
            return True

        return False

    def _compute_job_kind(self, ingress_event: GitHubIngressEvent) -> JobKind:
        if ingress_event.entity_type.value == 'issue':
            return JobKind.ISSUE

        if ingress_event.event_type == IngressEventType.PR_REVIEW_REQUESTED:
            return JobKind.PR_REVIEWER

        if ingress_event.event_type == IngressEventType.PR_CI_FAILED:
            return JobKind.PR_AUTHOR

        job_kind_hint = ingress_event.details.get('job_kind_hint')
        if job_kind_hint == JobKind.PR_REVIEWER.value:
            return JobKind.PR_REVIEWER

        pull_author_login = str(ingress_event.details.get('pull_author_login', '')).strip().lower()
        if (
            ingress_event.event_type == IngressEventType.PR_MENTION
            and pull_author_login != ''
            and pull_author_login != self._agent_actor
        ):
            return JobKind.PR_REVIEWER

        requires_follow_up = bool(ingress_event.details.get('requires_follow_up', False))
        if (
            ingress_event.event_type == IngressEventType.PR_UPDATED
            and requires_follow_up
            and pull_author_login != ''
            and pull_author_login != self._agent_actor
        ):
            return JobKind.PR_REVIEWER

        return JobKind.PR_AUTHOR

    def _compute_initial_state(self, ingress_event: GitHubIngressEvent) -> JobState:
        has_sufficient_context = bool(ingress_event.details.get('has_sufficient_context', True))
        if (
            ingress_event.event_type == IngressEventType.ISSUE_ASSIGNMENT
            and not has_sufficient_context
        ):
            return JobState.AWAITING_CONTEXT

        return JobState.READY_TO_EXECUTE

    def _compute_transition(self, ingress_event: GitHubIngressEvent) -> tuple[JobState | None, str | None]:
        issue_state = str(ingress_event.details.get('issue_state', '')).strip().lower()
        if ingress_event.entity_type.value == 'issue' and issue_state == 'closed':
            return JobState.COMPLETED, 'issue_human_terminal_decision_closed'

        pull_is_merged = ingress_event.details.get('pull_is_merged')
        if ingress_event.entity_type.value == 'pr' and pull_is_merged is True:
            return JobState.COMPLETED, 'pr_human_terminal_decision_merged'

        pull_state = str(ingress_event.details.get('pull_state', '')).strip().lower()
        if ingress_event.entity_type.value == 'pr' and pull_state == 'closed':
            return JobState.COMPLETED, 'pr_human_terminal_decision_closed'

        if ingress_event.event_type in (
            IngressEventType.ISSUE_MENTION,
            IngressEventType.PR_MENTION,
        ):
            return JobState.READY_TO_EXECUTE, ingress_event.event_type.value

        if ingress_event.event_type == IngressEventType.PR_REVIEW_REQUESTED:
            return JobState.READY_TO_EXECUTE, ingress_event.event_type.value

        if ingress_event.event_type == IngressEventType.ISSUE_UPDATED:
            has_sufficient_context = bool(ingress_event.details.get('has_sufficient_context', True))
            if has_sufficient_context:
                return JobState.READY_TO_EXECUTE, 'issue_updated_context_refresh'

            return None, None

        if ingress_event.event_type == IngressEventType.PR_REVIEW_COMMENT:
            job_kind_hint = ingress_event.details.get('job_kind_hint')
            if job_kind_hint == JobKind.PR_REVIEWER.value:
                is_review_thread_comment = bool(
                    ingress_event.details.get('is_review_thread_comment', False),
                )
                if is_review_thread_comment:
                    return JobState.READY_TO_EXECUTE, ingress_event.event_type.value

                return None, None

            return JobState.READY_TO_EXECUTE, ingress_event.event_type.value

        if ingress_event.event_type == IngressEventType.PR_CI_FAILED:
            return JobState.READY_TO_EXECUTE, ingress_event.event_type.value

        requires_follow_up = bool(ingress_event.details.get('requires_follow_up', False))
        if ingress_event.event_type == IngressEventType.PR_UPDATED and requires_follow_up:
            return JobState.READY_TO_EXECUTE, 'pr_updated_requires_follow_up'

        if ingress_event.event_type == IngressEventType.PR_UPDATED:
            terminal_decision = str(ingress_event.details.get('human_terminal_decision', '')).strip().lower()
            if terminal_decision in {'merged', 'closed'}:
                return JobState.COMPLETED, f"pr_human_terminal_decision_{terminal_decision}"

        return None, None

    def normalize_event(self, ingress_event: GitHubIngressEvent) -> NormalizedIngressEvent | None:

        '''
        Create deterministic normalized ingress event from raw GitHub ingress payload.

        Args:
        ingress_event (GitHubIngressEvent): Raw ingress event payload.

        Returns:
        NormalizedIngressEvent | None: Normalized event for orchestrator processing.
        '''

        if self._is_ignored_actor_event(ingress_event):
            return None
        if self._is_out_of_scope_event(ingress_event):
            return None

        job_kind = self._compute_job_kind(ingress_event)
        entity_key = f"{ingress_event.repository}#{ingress_event.entity_number}"
        job_id = (
            f"{ingress_event.repository.replace('/', '_')}"
            f"#{ingress_event.entity_number}:{job_kind.value}"
        )
        transition_to, transition_reason = self._compute_transition(ingress_event)
        is_sandbox_scope = self._is_sandbox_scope_event(ingress_event)

        return NormalizedIngressEvent(
            event_id=ingress_event.event_id,
            trace_id=(
                f"trc_{ingress_event.event_id}_"
                f"{int(ingress_event.timestamp.timestamp() * 1_000_000)}"
            ),
            environment=self._environment,
            repository=ingress_event.repository,
            entity_number=ingress_event.entity_number,
            entity_key=entity_key,
            job_id=job_id,
            job_kind=job_kind,
            initial_state=self._compute_initial_state(ingress_event),
            should_claim_lease=True,
            transition_to=transition_to,
            transition_reason=transition_reason,
            idempotency_key=(
                f"{ingress_event.event_id}:"
                f"{ingress_event.event_type.value}:"
                f"{ingress_event.timestamp.isoformat()}"
            ),
            details={
                'actor': ingress_event.actor,
                'ingress_event_type': ingress_event.event_type.value,
                'is_sandbox_scope': is_sandbox_scope,
                **ingress_event.details,
            },
        )

    def normalize_events(self, ingress_events: list[GitHubIngressEvent]) -> list[NormalizedIngressEvent]:

        '''
        Create normalized ingress event list from raw ingress event list.

        Args:
        ingress_events (list[GitHubIngressEvent]): Raw ingress events.

        Returns:
        list[NormalizedIngressEvent]: Normalized ingress events.
        '''

        normalized_events: list[NormalizedIngressEvent] = []
        for ingress_event in ingress_events:
            normalized_event = self.normalize_event(ingress_event)
            if normalized_event is not None:
                normalized_events.append(normalized_event)

        return normalized_events


__all__ = ['GitHubIngressNormalizer']
