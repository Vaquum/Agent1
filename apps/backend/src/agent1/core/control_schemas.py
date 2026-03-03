from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

from agent1.core.contracts import EnvironmentName
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobState
from agent1.core.contracts import RuntimeMode


class PromptTemplate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    system_prompt: str = Field(min_length=1)
    task_prompt: str = Field(min_length=1)


class PromptsControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    templates: dict[str, PromptTemplate] = Field(min_length=1)


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    allow: bool


class MutatingCredentialOwnerByEnvironment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    dev: str = Field(min_length=1)
    prod: str = Field(min_length=1)
    ci: str = Field(min_length=1)


class GitHubCapabilities(BaseModel):
    model_config = ConfigDict(extra='forbid')

    read_notifications: bool
    read_pr_timeline: bool
    read_pr_check_runs: bool
    read_issue: bool
    read_pull_request: bool
    write_issue_comment: bool
    write_pr_review_reply: bool


class BranchMutationPatternsByEnvironment(BaseModel):
    model_config = ConfigDict(extra='forbid')

    dev: list[str] = Field(min_length=1)
    prod: list[str] = Field(min_length=1)
    ci: list[str] = Field(min_length=1)


class PermissionMatrixEntryControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    component: Literal['api', 'worker', 'watcher', 'dashboard', 'ci']
    environment: EnvironmentName
    permissions: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_permissions(self) -> 'PermissionMatrixEntryControl':
        normalized_permissions = [permission.strip() for permission in self.permissions]
        if any(permission == '' for permission in normalized_permissions):
            message = (
                'Permission matrix contains empty permission entry for '
                f'{self.component}:{self.environment.value}'
            )
            raise ValueError(message)
        if len(normalized_permissions) != len(set(normalized_permissions)):
            message = (
                'Permission matrix contains duplicate permissions for '
                f'{self.component}:{self.environment.value}'
            )
            raise ValueError(message)

        return self


class PermissionMatrixPersistenceRolesControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    migrator: list[str] = Field(min_length=1)
    runtime: list[str] = Field(min_length=1)
    readonly_analytics: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_role_permissions(self) -> 'PermissionMatrixPersistenceRolesControl':
        role_permissions = {
            'migrator': self.migrator,
            'runtime': self.runtime,
            'readonly_analytics': self.readonly_analytics,
        }
        for role_name, permissions in role_permissions.items():
            normalized_permissions = [permission.strip() for permission in permissions]
            if any(permission == '' for permission in normalized_permissions):
                message = f'Permission matrix role {role_name} contains empty permission entry.'
                raise ValueError(message)
            if len(normalized_permissions) != len(set(normalized_permissions)):
                message = f'Permission matrix role {role_name} contains duplicate permissions.'
                raise ValueError(message)

        return self


class PermissionMatrixControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    entries: list[PermissionMatrixEntryControl] = Field(min_length=1)
    persistence_roles: PermissionMatrixPersistenceRolesControl

    @model_validator(mode='after')
    def validate_matrix_coverage(self) -> 'PermissionMatrixControl':
        seen_pairs: set[tuple[str, str]] = set()
        for entry in self.entries:
            entry_pair = (entry.component, entry.environment.value)
            if entry_pair in seen_pairs:
                message = (
                    'Permission matrix contains duplicate component/environment pair: '
                    f'{entry.component}:{entry.environment.value}'
                )
                raise ValueError(message)
            seen_pairs.add(entry_pair)

        required_components = {'api', 'worker', 'watcher', 'dashboard', 'ci'}
        required_environments = {
            EnvironmentName.DEV.value,
            EnvironmentName.PROD.value,
            EnvironmentName.CI.value,
        }
        missing_pairs: list[str] = []
        for component in sorted(required_components):
            for environment in sorted(required_environments):
                required_pair = (component, environment)
                if required_pair not in seen_pairs:
                    missing_pairs.append(f'{component}:{environment}')

        if len(missing_pairs) != 0:
            message = (
                'Permission matrix missing component/environment entries: '
                + ', '.join(missing_pairs)
            )
            raise ValueError(message)

        return self


class ProtectedMutationFileDigestControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class ProtectedMutationActiveSnapshotControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    approval_id: str = Field(min_length=1)
    change_ticket: str = Field(min_length=1)
    approved_by: list[str] = Field(min_length=1)
    approved_at: datetime
    reason: str = Field(min_length=1)
    protected_files: list[ProtectedMutationFileDigestControl] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_active_snapshot(self) -> 'ProtectedMutationActiveSnapshotControl':
        normalized_approvers = [approver.strip() for approver in self.approved_by]
        if any(approver == '' for approver in normalized_approvers):
            message = 'Protected-mutation approval snapshot contains empty approver identity.'
            raise ValueError(message)
        if len(normalized_approvers) != len(set(normalized_approvers)):
            message = 'Protected-mutation approval snapshot contains duplicate approver identity.'
            raise ValueError(message)

        normalized_paths = [protected_file.path.strip() for protected_file in self.protected_files]
        if any(path == '' for path in normalized_paths):
            message = 'Protected-mutation approval snapshot contains empty protected-file path.'
            raise ValueError(message)
        if len(normalized_paths) != len(set(normalized_paths)):
            message = 'Protected-mutation approval snapshot contains duplicate protected-file path.'
            raise ValueError(message)

        return self


class ProtectedMutationAuditTrailEntryControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    event_id: str = Field(min_length=1)
    approval_id: str = Field(min_length=1)
    decision: Literal['approved', 'revoked']
    recorded_at: datetime
    recorded_by: str = Field(min_length=1)
    note: str = Field(min_length=1)


class ProtectedMutationApprovalControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    active_snapshot: ProtectedMutationActiveSnapshotControl
    audit_trail: list[ProtectedMutationAuditTrailEntryControl] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_audit_trail(self) -> 'ProtectedMutationApprovalControl':
        event_ids: set[str] = set()
        for audit_entry in self.audit_trail:
            if audit_entry.event_id in event_ids:
                message = (
                    'Protected-mutation approval audit trail contains duplicate event id: '
                    f'{audit_entry.event_id}'
                )
                raise ValueError(message)
            event_ids.add(audit_entry.event_id)

        matching_entries = [
            audit_entry
            for audit_entry in self.audit_trail
            if audit_entry.approval_id == self.active_snapshot.approval_id
        ]
        if len(matching_entries) == 0:
            message = (
                'Protected-mutation approval audit trail is missing active approval id: '
                f'{self.active_snapshot.approval_id}'
            )
            raise ValueError(message)

        latest_entry = max(
            matching_entries,
            key=lambda audit_entry: audit_entry.recorded_at,
        )
        if latest_entry.decision != 'approved':
            message = (
                'Protected-mutation approval audit trail latest decision is not approved '
                f'for active approval id {self.active_snapshot.approval_id}.'
            )
            raise ValueError(message)

        return self


class PoliciesControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    repo_scope: list[str] = Field(min_length=1)
    agent_actor: str = Field(default='zero-bang', min_length=1)
    ignored_actors: list[str] = Field(default_factory=list)
    ignored_actor_suffixes: list[str] = Field(default_factory=lambda: ['[bot]'])
    deny_git_commands: list[str] = Field(default_factory=list)
    allowed_git_mutation_commands: list[str] = Field(default_factory=list)
    branch_mutation_patterns_by_environment: BranchMutationPatternsByEnvironment
    permission_matrix: PermissionMatrixControl
    protected_mutation_approval: ProtectedMutationApprovalControl
    enforce_read_write_credential_split: bool
    default_deny_github_capabilities: bool
    fail_closed_policy_resolution: bool
    mutating_credential_owner_by_environment: MutatingCredentialOwnerByEnvironment
    github_capabilities: GitHubCapabilities
    rules: list[PolicyRule] = Field(default_factory=list)


class StylesControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    coding_style: str = Field(min_length=1)
    communication_style: str = Field(min_length=1)


class CommentingControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    require_review_thread_reply: bool
    allow_top_level_pr_fallback: bool
    issue_comment_mode: str = Field(min_length=1)


class JobLifecycleRule(BaseModel):
    model_config = ConfigDict(extra='forbid')

    job_kind: JobKind
    terminal_states: list[JobState] = Field(min_length=1)


class JobsControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    rules: list[JobLifecycleRule] = Field(min_length=1)


class RolloutHealthSignalControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    signal_id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class RolloutStageControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    stage_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required_health_signals: list[str] = Field(min_length=1)


class RolloutPolicyControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    health_signals: list[RolloutHealthSignalControl] = Field(min_length=1)
    stages: list[RolloutStageControl] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_rollout_references(self) -> 'RolloutPolicyControl':
        signal_ids: set[str] = set()
        for signal in self.health_signals:
            if signal.signal_id in signal_ids:
                message = f'Duplicate rollout health signal id: {signal.signal_id}'
                raise ValueError(message)
            signal_ids.add(signal.signal_id)

        stage_ids: set[str] = set()
        for stage in self.stages:
            if stage.stage_id in stage_ids:
                message = f'Duplicate rollout stage id: {stage.stage_id}'
                raise ValueError(message)
            stage_ids.add(stage.stage_id)

            for required_signal_id in stage.required_health_signals:
                if required_signal_id not in signal_ids:
                    message = (
                        'Unknown rollout health signal in stage '
                        f'{stage.stage_id}: {required_signal_id}'
                    )
                    raise ValueError(message)

        return self


class StopTheLineThresholdRuleControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    signal_id: str = Field(min_length=1)
    comparator: Literal['gt', 'gte', 'lt', 'lte']
    threshold: float = Field(ge=0.0)
    evaluation_window_minutes: int = Field(gt=0)


class StopTheLinePolicyControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rules: list[StopTheLineThresholdRuleControl] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_unique_rule_signals(self) -> 'StopTheLinePolicyControl':
        signal_ids: set[str] = set()
        for rule in self.rules:
            if rule.signal_id in signal_ids:
                message = f'Duplicate stop-the-line rule signal id: {rule.signal_id}'
                raise ValueError(message)
            signal_ids.add(rule.signal_id)

        return self


class ReleasePromotionPreconditionControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    precondition_id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ReleasePromotionPolicyControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    preconditions: list[ReleasePromotionPreconditionControl] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_unique_precondition_ids(self) -> 'ReleasePromotionPolicyControl':
        precondition_ids: set[str] = set()
        for precondition in self.preconditions:
            if precondition.precondition_id in precondition_ids:
                message = (
                    'Duplicate release-promotion precondition id: '
                    f'{precondition.precondition_id}'
                )
                raise ValueError(message)
            precondition_ids.add(precondition.precondition_id)

        return self


class RuntimeControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    mode: RuntimeMode
    active_repositories: list[str] = Field(min_length=1)
    require_sandbox_scope_for_dev_active: bool
    sandbox_label: str = Field(min_length=1)
    sandbox_branch_prefix: str = Field(min_length=1)
    poll_interval_seconds: int = Field(gt=0)
    watch_interval_seconds: int = Field(gt=0)
    max_retry_attempts: int = Field(ge=0)
    rollout_policy: RolloutPolicyControl
    stop_the_line_policy: StopTheLinePolicyControl
    release_promotion_policy: ReleasePromotionPolicyControl


class ControlBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    prompts: PromptsControl
    policies: PoliciesControl
    styles: StylesControl
    commenting: CommentingControl
    jobs: JobsControl
    runtime: RuntimeControl


__all__ = [
    'BranchMutationPatternsByEnvironment',
    'CommentingControl',
    'ControlBundle',
    'GitHubCapabilities',
    'JobsControl',
    'MutatingCredentialOwnerByEnvironment',
    'PermissionMatrixControl',
    'PermissionMatrixEntryControl',
    'PermissionMatrixPersistenceRolesControl',
    'ProtectedMutationActiveSnapshotControl',
    'ProtectedMutationApprovalControl',
    'ProtectedMutationAuditTrailEntryControl',
    'ProtectedMutationFileDigestControl',
    'PoliciesControl',
    'PromptsControl',
    'RuntimeControl',
    'RolloutHealthSignalControl',
    'RolloutPolicyControl',
    'RolloutStageControl',
    'ReleasePromotionPreconditionControl',
    'ReleasePromotionPolicyControl',
    'StopTheLinePolicyControl',
    'StopTheLineThresholdRuleControl',
    'StylesControl',
]
