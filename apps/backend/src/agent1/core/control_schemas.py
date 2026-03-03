from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

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


class PoliciesControl(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: str = Field(min_length=1)
    repo_scope: list[str] = Field(min_length=1)
    agent_actor: str = Field(default='zero-bang', min_length=1)
    ignored_actors: list[str] = Field(default_factory=list)
    ignored_actor_suffixes: list[str] = Field(default_factory=lambda: ['[bot]'])
    deny_git_commands: list[str] = Field(default_factory=list)
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


class ControlBundle(BaseModel):
    model_config = ConfigDict(extra='forbid')

    prompts: PromptsControl
    policies: PoliciesControl
    styles: StylesControl
    commenting: CommentingControl
    jobs: JobsControl
    runtime: RuntimeControl


__all__ = [
    'CommentingControl',
    'ControlBundle',
    'GitHubCapabilities',
    'JobsControl',
    'MutatingCredentialOwnerByEnvironment',
    'PoliciesControl',
    'PromptsControl',
    'RuntimeControl',
    'StylesControl',
]
