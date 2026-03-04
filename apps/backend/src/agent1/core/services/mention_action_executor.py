from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Protocol
from urllib.error import HTTPError

from agent1.adapters.github.client import GitHubApiClient
from agent1.adapters.github.client import UrlLibGitHubApiClient
from agent1.config.settings import get_settings
from agent1.core.contracts import CommentTarget
from agent1.core.contracts import CommentTargetRecord
from agent1.core.contracts import CommentTargetType
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus
from agent1.core.contracts import JobKind
from agent1.core.contracts import JobRecord
from agent1.core.contracts import JobState
from agent1.core.contracts import OutboxActionType
from agent1.core.contracts import OutboxRecord
from agent1.core.contracts import OutboxStatus
from agent1.core.contracts import OutboxWriteRequest
from agent1.core.contracts import RuntimeMode
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import NormalizedIngressEvent
from agent1.core.orchestrator import JobOrchestrator
from agent1.core.services.comment_router import CommentRouter
from agent1.core.services.comment_router import CommentRoutingError
from agent1.core.services.idempotency_schema import IDEMPOTENCY_DEFAULT_POLICY_VERSION
from agent1.core.services.idempotency_schema import build_canonical_idempotency_scope
from agent1.core.services.telemetry_runtime import get_tracer

MENTION_EXECUTION_START_REASON = 'mention_action_started'
MENTION_RESPONSE_POSTED_REASON = 'mention_response_posted'
MENTION_RESPONSE_FAILED_REASON = 'mention_response_failed'
INTERACTION_CODEX_EXECUTION_FAILED_REASON = 'interaction_codex_execution_failed'
INTERACTION_CODEX_EXECUTION_BLOCKED_REASON = 'interaction_codex_execution_blocked'
COMMENT_ROUTE_FAILED_REASON = 'comment_route_failed'
CLARIFICATION_REQUEST_POSTED_REASON = 'clarification_request_posted'
CLARIFICATION_REQUEST_FAILED_REASON = 'clarification_request_failed'
REVIEWER_EXECUTION_START_REASON = 'reviewer_action_started'
REVIEWER_RESPONSE_POSTED_REASON = 'reviewer_response_posted'
REVIEWER_RESPONSE_FAILED_REASON = 'reviewer_response_failed'
REVIEWER_CODEX_EXECUTION_FAILED_REASON = 'reviewer_codex_execution_failed'
REVIEWER_CODEX_EXECUTION_BLOCKED_REASON = 'reviewer_codex_execution_blocked'
AUTHOR_EXECUTION_START_REASON = 'author_action_started'
AUTHOR_FEEDBACK_POSTED_REASON = 'author_feedback_posted'
AUTHOR_CI_TRIAGE_POSTED_REASON = 'author_ci_triage_posted'
AUTHOR_RESPONSE_FAILED_REASON = 'author_response_failed'
AUTHOR_CODEX_EXECUTION_FAILED_REASON = 'author_codex_execution_failed'
AUTHOR_CODEX_EXECUTION_BLOCKED_REASON = 'author_codex_execution_blocked'
NO_WRITE_CLARIFICATION_REASON = 'no_write_clarification_observed'
NO_WRITE_EXECUTION_START_REASON = 'no_write_execution_started'
NO_WRITE_FEEDBACK_REASON = 'no_write_feedback_observed'
NO_WRITE_CI_REASON = 'no_write_ci_observed'
COMMENT_TARGET_OUTBOX_ABORT_REASON = 'comment_target_delivery_failed'
REVIEWER_PROMPT_MAX_PATCH_CHARACTERS = 80_000
REVIEWER_PROMPT_MAX_FILE_COUNT = 80
CODEX_REPOSITORY_WORKSPACE_ROOT = '/tmp/agent1-repository-workspaces'
GIT_COMMAND_TIMEOUT_SECONDS = 60
REVIEWER_JSON_CODE_FENCE_PATTERN = re.compile(
    r'^```(?:json)?\s*(?P<body>[\s\S]*?)\s*```$',
    flags=re.IGNORECASE,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_error_details(error: Exception) -> dict[str, object]:
    error_details: dict[str, object] = {
        'error_type': error.__class__.__name__,
        'error_message': str(error),
    }
    if isinstance(error, HTTPError):
        error_details['http_status'] = error.code
        error_details['http_reason'] = str(error.reason)
        try:
            error_payload = error.read().decode('utf-8').strip()
        except Exception:
            error_payload = ''
        if error_payload != '':
            error_details['http_body'] = error_payload[:2000]

    return error_details


def _build_transition_error_details(
    error: Exception,
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    transition_error_details = _serialize_error_details(error)
    if context is not None:
        transition_error_details.update(context)

    return transition_error_details


def _extract_codex_stdout_text(execution_result: ExecutionResult) -> str:
    last_message_value = execution_result.metadata.get('last_message')
    if isinstance(last_message_value, str):
        normalized_last_message = last_message_value.strip()
        if normalized_last_message != '':
            return normalized_last_message

    stdout_value = execution_result.metadata.get('stdout')
    stdout_lines: list[str] = []
    if isinstance(stdout_value, list):
        stdout_lines.extend(
            line
            for line in stdout_value
            if isinstance(line, str)
        )
    elif isinstance(stdout_value, str):
        stdout_lines.append(stdout_value)

    stdout_text = '\n'.join(stdout_lines).strip()
    if stdout_text == '':
        raise ValueError('Codex execution returned empty stdout output.')

    return stdout_text


def _strip_json_code_fence(payload: str) -> str:
    normalized_payload = payload.strip()
    code_fence_match = REVIEWER_JSON_CODE_FENCE_PATTERN.match(normalized_payload)
    if code_fence_match is None:
        return normalized_payload

    return code_fence_match.group('body').strip()


def _extract_right_side_patch_lines(file_patch: str) -> set[int]:
    reviewable_lines: set[int] = set()
    current_right_line: int | None = None
    hunk_header_pattern = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
    for patch_line in file_patch.splitlines():
        if patch_line.startswith('@@'):
            hunk_header_match = hunk_header_pattern.match(patch_line)
            if hunk_header_match is None:
                message = f'Invalid unified diff hunk header: {patch_line}'
                raise ValueError(message)
            current_right_line = int(hunk_header_match.group(1))
            continue

        if current_right_line is None:
            continue

        if patch_line.startswith('+') or patch_line.startswith(' '):
            reviewable_lines.add(current_right_line)
            current_right_line += 1
            continue
        if patch_line.startswith('-') or patch_line.startswith('\\'):
            continue

        message = f'Unsupported patch line prefix: {patch_line[:1]}'
        raise ValueError(message)

    return reviewable_lines


def _collect_reviewable_lines_by_path(pull_files: list[dict[str, object]]) -> dict[str, set[int]]:
    reviewable_lines_by_path: dict[str, set[int]] = {}
    for pull_file in pull_files:
        filename_value = pull_file.get('filename')
        if not isinstance(filename_value, str) or filename_value.strip() == '':
            message = 'Pull request file payload is missing a valid filename.'
            raise ValueError(message)

        file_patch_value = pull_file.get('patch')
        if not isinstance(file_patch_value, str) or file_patch_value.strip() == '':
            continue

        reviewable_lines_by_path[filename_value] = _extract_right_side_patch_lines(file_patch_value)

    return reviewable_lines_by_path


def _parse_inline_review_payload(
    reviewer_output: str,
) -> tuple[str, list[dict[str, object]]]:
    payload_text = _strip_json_code_fence(reviewer_output)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as error:
        message = f'Reviewer output is not valid JSON: {error}'
        raise ValueError(message) from error

    if not isinstance(payload, dict):
        message = 'Reviewer output JSON must be an object.'
        raise ValueError(message)

    summary_value = payload.get('summary')
    if not isinstance(summary_value, str) or summary_value.strip() == '':
        message = 'Reviewer output JSON must include non-empty `summary`.'
        raise ValueError(message)
    summary = summary_value.strip()

    comments_value = payload.get('comments')
    if not isinstance(comments_value, list):
        message = 'Reviewer output JSON must include `comments` as a list.'
        raise ValueError(message)

    parsed_comments: list[dict[str, object]] = []
    for comment_index, comment_value in enumerate(comments_value):
        if not isinstance(comment_value, dict):
            message = f'Reviewer comment at index {comment_index} must be an object.'
            raise ValueError(message)

        path_value = comment_value.get('path')
        if not isinstance(path_value, str) or path_value.strip() == '':
            message = f'Reviewer comment at index {comment_index} is missing non-empty `path`.'
            raise ValueError(message)

        line_value = comment_value.get('line')
        if not isinstance(line_value, int) or line_value <= 0:
            message = f'Reviewer comment at index {comment_index} has invalid `line`.'
            raise ValueError(message)

        body_value = comment_value.get('body')
        if not isinstance(body_value, str) or body_value.strip() == '':
            message = f'Reviewer comment at index {comment_index} is missing non-empty `body`.'
            raise ValueError(message)

        side_value = comment_value.get('side')
        if side_value is None:
            side = 'RIGHT'
        elif isinstance(side_value, str):
            side = side_value.strip().upper()
            if side == '':
                side = 'RIGHT'
        else:
            message = f'Reviewer comment at index {comment_index} has invalid `side`.'
            raise ValueError(message)

        if side != 'RIGHT':
            message = f'Reviewer comment at index {comment_index} must use `side=RIGHT`.'
            raise ValueError(message)

        parsed_comments.append(
            {
                'path': path_value.strip(),
                'line': line_value,
                'side': 'RIGHT',
                'body': body_value.strip(),
            }
        )

    return summary, parsed_comments


def _validate_inline_review_comments(
    comments_payload: list[dict[str, object]],
    reviewable_lines_by_path: dict[str, set[int]],
) -> list[dict[str, object]]:
    validated_comments: list[dict[str, object]] = []
    for comment_index, comment_payload in enumerate(comments_payload):
        path_value = comment_payload.get('path')
        line_value = comment_payload.get('line')
        body_value = comment_payload.get('body')
        side_value = comment_payload.get('side')
        if (
            not isinstance(path_value, str)
            or not isinstance(line_value, int)
            or not isinstance(body_value, str)
            or not isinstance(side_value, str)
        ):
            message = f'Reviewer comment at index {comment_index} has invalid payload shape.'
            raise ValueError(message)

        reviewable_lines = reviewable_lines_by_path.get(path_value)
        if reviewable_lines is None:
            message = f'Reviewer comment path is not reviewable in PR diff: {path_value}'
            raise ValueError(message)
        if line_value not in reviewable_lines:
            message = (
                f'Reviewer comment line is not reviewable in PR diff: '
                f'{path_value}:{line_value}'
            )
            raise ValueError(message)

        validated_comments.append(
            {
                'path': path_value,
                'line': line_value,
                'side': side_value,
                'body': body_value,
            }
        )

    return validated_comments


def _render_prompt_template(
    template_name: str,
    template_value: str,
    template_values: dict[str, object],
) -> str:
    normalized_template = template_value.strip()
    if normalized_template == '':
        message = f'Prompt template is empty: {template_name}'
        raise ValueError(message)

    try:
        return normalized_template.format(**template_values)
    except KeyError as error:
        missing_key = str(error).strip("'")
        message = f'Prompt template {template_name} is missing format key: {missing_key}'
        raise ValueError(message) from error


def _is_supported_comment_event(normalized_event: NormalizedIngressEvent) -> bool:
    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    if ingress_event_type == IngressEventType.ISSUE_ASSIGNMENT.value:
        return bool(normalized_event.details.get('has_sufficient_context', True))

    return ingress_event_type in {
        IngressEventType.ISSUE_MENTION.value,
        IngressEventType.ISSUE_UPDATED.value,
        IngressEventType.PR_MENTION.value,
        IngressEventType.PR_REVIEW_COMMENT.value,
    }


def _is_clarification_event(normalized_event: NormalizedIngressEvent) -> bool:
    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    has_sufficient_context = bool(normalized_event.details.get('has_sufficient_context', True))
    return (
        ingress_event_type == IngressEventType.ISSUE_ASSIGNMENT.value
        and has_sufficient_context is False
    )


def _is_reviewer_event(normalized_event: NormalizedIngressEvent, current_job: JobRecord) -> bool:
    if current_job.kind != JobKind.PR_REVIEWER:
        return False

    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    if ingress_event_type == IngressEventType.PR_REVIEW_REQUESTED.value:
        return True
    if ingress_event_type == IngressEventType.PR_UPDATED.value:
        return bool(normalized_event.details.get('requires_follow_up', False))

    return False


def _is_reviewer_thread_reply_event(
    normalized_event: NormalizedIngressEvent,
    current_job: JobRecord,
) -> bool:
    if current_job.kind != JobKind.PR_REVIEWER:
        return False

    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    if ingress_event_type != IngressEventType.PR_REVIEW_COMMENT.value:
        return False

    return bool(normalized_event.details.get('is_review_thread_comment', False))


def _is_author_feedback_event(normalized_event: NormalizedIngressEvent, current_job: JobRecord) -> bool:
    if current_job.kind != JobKind.PR_AUTHOR:
        return False

    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    if ingress_event_type == IngressEventType.PR_REVIEW_COMMENT.value:
        return True
    if ingress_event_type == IngressEventType.PR_UPDATED.value:
        return bool(normalized_event.details.get('requires_follow_up', False))

    return False


def _is_author_ci_event(normalized_event: NormalizedIngressEvent, current_job: JobRecord) -> bool:
    if current_job.kind != JobKind.PR_AUTHOR:
        return False

    ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
    return ingress_event_type == IngressEventType.PR_CI_FAILED.value


class CodexTaskExecutor(Protocol):
    def execute_task(
        self,
        task_id: str,
        prompt: str,
    ) -> ExecutionResult:
        ...


class MentionActionExecutor:
    def __init__(
        self,
        response_template: str,
        clarification_template: str,
        reviewer_follow_up_template: str,
        author_follow_up_template: str,
        issue_mention_codex_prompt_template: str = '',
        pr_mention_codex_prompt_template: str = '',
        issue_assignment_codex_prompt_template: str = '',
        reviewer_codex_review_prompt_template: str = '',
        reviewer_codex_thread_reply_prompt_template: str = '',
        author_codex_prompt_template: str = '',
        require_review_thread_reply: bool = True,
        allow_top_level_pr_fallback: bool = False,
        idempotency_policy_version: str = IDEMPOTENCY_DEFAULT_POLICY_VERSION,
        github_client: GitHubApiClient | None = None,
        codex_executor: CodexTaskExecutor | None = None,
    ) -> None:
        self._response_template = response_template
        self._clarification_template = clarification_template
        self._reviewer_follow_up_template = reviewer_follow_up_template
        self._reviewer_codex_review_prompt_template = reviewer_codex_review_prompt_template
        self._reviewer_codex_thread_reply_prompt_template = (
            reviewer_codex_thread_reply_prompt_template
        )
        self._author_follow_up_template = author_follow_up_template
        self._issue_mention_codex_prompt_template = issue_mention_codex_prompt_template
        self._pr_mention_codex_prompt_template = pr_mention_codex_prompt_template
        self._issue_assignment_codex_prompt_template = issue_assignment_codex_prompt_template
        self._author_codex_prompt_template = author_codex_prompt_template
        self._comment_router = CommentRouter(
            require_review_thread_reply=require_review_thread_reply,
            allow_top_level_pr_fallback=allow_top_level_pr_fallback,
        )
        self._idempotency_policy_version = idempotency_policy_version
        self._github_client = github_client or UrlLibGitHubApiClient()
        self._codex_executor = codex_executor

    def _run_git_command(
        self,
        command: list[str],
        working_directory: Path | None = None,
    ) -> bool:
        try:
            completed_process = subprocess.run(
                command,
                cwd=str(working_directory) if working_directory is not None else None,
                capture_output=True,
                text=True,
                timeout=GIT_COMMAND_TIMEOUT_SECONDS,
                check=False,
            )
        except Exception:
            return False

        return completed_process.returncode == 0

    def _resolve_author_codex_working_directory(
        self,
        normalized_event: NormalizedIngressEvent,
    ) -> str | None:
        head_ref = str(normalized_event.details.get('head_ref', '')).strip()
        repository = normalized_event.repository.strip()
        if head_ref == '' or repository == '':
            return None

        runtime_settings = get_settings()
        github_token = runtime_settings.github_token.strip()
        if github_token == '':
            return None

        repository_workspace_root = Path(CODEX_REPOSITORY_WORKSPACE_ROOT)
        repository_workspace_root.mkdir(parents=True, exist_ok=True)
        repository_workspace = repository_workspace_root / repository.replace('/', '_')
        remote_url = (
            f"https://x-access-token:{github_token}@github.com/{repository}.git"
        )
        repository_git_directory = repository_workspace / '.git'
        if repository_git_directory.exists() is False:
            cloned = self._run_git_command(
                ['git', 'clone', remote_url, str(repository_workspace)],
            )
            if cloned is False:
                return None
        else:
            origin_updated = self._run_git_command(
                ['git', 'remote', 'set-url', 'origin', remote_url],
                working_directory=repository_workspace,
            )
            if origin_updated is False:
                return None

        fetched_branch = self._run_git_command(
            ['git', 'fetch', 'origin', head_ref],
            working_directory=repository_workspace,
        )
        if fetched_branch is False:
            return None

        checked_out_branch = self._run_git_command(
            ['git', 'checkout', '-B', head_ref, f'origin/{head_ref}'],
            working_directory=repository_workspace,
        )
        if checked_out_branch is False:
            return None

        git_user_name = runtime_settings.github_user.strip()
        if git_user_name == '':
            git_user_name = os.getenv('GITHUB_USER', '').strip()
        if git_user_name == '':
            git_user_name = 'agent1'
        git_user_email = f'{git_user_name}@users.noreply.github.com'
        self._run_git_command(
            ['git', 'config', 'user.name', git_user_name],
            working_directory=repository_workspace,
        )
        self._run_git_command(
            ['git', 'config', 'user.email', git_user_email],
            working_directory=repository_workspace,
        )
        return str(repository_workspace)

    def _build_author_codex_prompt(self, normalized_event: NormalizedIngressEvent) -> str:
        ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
        check_name = str(normalized_event.details.get('check_name', ''))
        conclusion = str(normalized_event.details.get('conclusion', ''))
        return _render_prompt_template(
            template_name='author_codex_follow_up',
            template_value=self._author_codex_prompt_template,
            template_values={
                'repository': normalized_event.repository,
                'entity_key': normalized_event.entity_key,
                'ingress_event_type': ingress_event_type,
                'check_name': check_name,
                'conclusion': conclusion,
            },
        )

    def _build_issue_context_template_values(
        self,
        normalized_event: NormalizedIngressEvent,
    ) -> dict[str, object]:
        issue_payload = self._github_client.fetch_issue(
            repository=normalized_event.repository,
            issue_number=normalized_event.entity_number,
        )
        issue_title = ''
        issue_body = ''
        issue_state = ''
        issue_assignees: list[str] = []
        issue_labels: list[str] = []
        if isinstance(issue_payload, dict):
            title_value = issue_payload.get('title')
            if isinstance(title_value, str):
                issue_title = title_value
            body_value = issue_payload.get('body')
            if isinstance(body_value, str):
                issue_body = body_value
            state_value = issue_payload.get('state')
            if isinstance(state_value, str):
                issue_state = state_value
            assignees_value = issue_payload.get('assignees')
            if isinstance(assignees_value, list):
                for assignee in assignees_value:
                    if not isinstance(assignee, dict):
                        continue
                    login_value = assignee.get('login')
                    if isinstance(login_value, str) and login_value.strip() != '':
                        issue_assignees.append(login_value.strip())
            labels_value = issue_payload.get('labels')
            if isinstance(labels_value, list):
                for label in labels_value:
                    if not isinstance(label, dict):
                        continue
                    label_name_value = label.get('name')
                    if isinstance(label_name_value, str) and label_name_value.strip() != '':
                        issue_labels.append(label_name_value.strip())

        ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
        has_sufficient_context = bool(normalized_event.details.get('has_sufficient_context', True))
        return {
            'repository': normalized_event.repository,
            'entity_key': normalized_event.entity_key,
            'ingress_event_type': ingress_event_type,
            'issue_title': issue_title,
            'issue_body': issue_body,
            'issue_state': issue_state,
            'issue_assignees': ', '.join(issue_assignees),
            'issue_labels': ', '.join(issue_labels),
            'has_sufficient_context': has_sufficient_context,
        }

    def _build_pr_context_template_values(
        self,
        normalized_event: NormalizedIngressEvent,
    ) -> dict[str, object]:
        pull_payload = self._github_client.fetch_pull_request(
            repository=normalized_event.repository,
            pull_number=normalized_event.entity_number,
        )
        pull_title = ''
        pull_body = ''
        pull_state = ''
        pull_base_ref = ''
        pull_head_ref = ''
        pull_changed_files = 0
        pull_additions = 0
        pull_deletions = 0
        pull_commits = 0
        if isinstance(pull_payload, dict):
            title_value = pull_payload.get('title')
            if isinstance(title_value, str):
                pull_title = title_value
            body_value = pull_payload.get('body')
            if isinstance(body_value, str):
                pull_body = body_value
            state_value = pull_payload.get('state')
            if isinstance(state_value, str):
                pull_state = state_value
            changed_files_value = pull_payload.get('changed_files')
            if isinstance(changed_files_value, int):
                pull_changed_files = changed_files_value
            additions_value = pull_payload.get('additions')
            if isinstance(additions_value, int):
                pull_additions = additions_value
            deletions_value = pull_payload.get('deletions')
            if isinstance(deletions_value, int):
                pull_deletions = deletions_value
            commits_value = pull_payload.get('commits')
            if isinstance(commits_value, int):
                pull_commits = commits_value
            base_payload = pull_payload.get('base')
            if isinstance(base_payload, dict):
                base_ref_value = base_payload.get('ref')
                if isinstance(base_ref_value, str):
                    pull_base_ref = base_ref_value
            head_payload = pull_payload.get('head')
            if isinstance(head_payload, dict):
                head_ref_value = head_payload.get('ref')
                if isinstance(head_ref_value, str):
                    pull_head_ref = head_ref_value

        ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
        return {
            'repository': normalized_event.repository,
            'entity_key': normalized_event.entity_key,
            'ingress_event_type': ingress_event_type,
            'pull_title': pull_title,
            'pull_body': pull_body,
            'pull_state': pull_state,
            'pull_base_ref': pull_base_ref,
            'pull_head_ref': pull_head_ref,
            'pull_changed_files': pull_changed_files,
            'pull_additions': pull_additions,
            'pull_deletions': pull_deletions,
            'pull_commits': pull_commits,
        }

    def _build_interaction_codex_prompt(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
    ) -> str:
        ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
        if ingress_event_type == IngressEventType.ISSUE_ASSIGNMENT.value:
            return _render_prompt_template(
                template_name='issue_assignment_codex',
                template_value=self._issue_assignment_codex_prompt_template,
                template_values=self._build_issue_context_template_values(normalized_event),
            )

        if current_job.kind == JobKind.ISSUE:
            return _render_prompt_template(
                template_name='issue_mention_codex',
                template_value=self._issue_mention_codex_prompt_template,
                template_values=self._build_issue_context_template_values(normalized_event),
            )

        if ingress_event_type == IngressEventType.PR_MENTION.value:
            return _render_prompt_template(
                template_name='pr_mention_codex',
                template_value=self._pr_mention_codex_prompt_template,
                template_values=self._build_pr_context_template_values(normalized_event),
            )

        message = (
            'Unsupported interaction codex event for mention/assignment execution: '
            f'{ingress_event_type}'
        )
        raise ValueError(message)

    def _execute_interaction_codex_task(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
    ) -> ExecutionResult | None:
        if self._codex_executor is None:
            return None

        task_id = (
            f"{current_job.job_id}:"
            f"{normalized_event.idempotency_key}:"
            'interaction_follow_up'
        )
        try:
            return self._codex_executor.execute_task(
                task_id=task_id,
                prompt=self._build_interaction_codex_prompt(normalized_event, current_job),
            )
        except Exception as error:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                summary='codex execution raised an exception',
                metadata=_build_transition_error_details(
                    error,
                    context={
                        'task_id': task_id,
                    },
                ),
            )

    def _build_reviewer_diff_context(
        self,
        normalized_event: NormalizedIngressEvent,
    ) -> tuple[str, int]:
        pull_files = self._github_client.fetch_pull_request_files(
            repository=normalized_event.repository,
            pull_number=normalized_event.entity_number,
        )
        if len(pull_files) == 0:
            return 'No pull request file diff context was returned by GitHub API.', 0

        included_file_count = 0
        used_patch_characters = 0
        diff_sections: list[str] = []
        for pull_file in pull_files:
            if included_file_count >= REVIEWER_PROMPT_MAX_FILE_COUNT:
                diff_sections.append('... [diff context truncated by file-count limit]')
                break

            filename_value = pull_file.get('filename')
            filename = filename_value if isinstance(filename_value, str) else 'unknown'
            status_value = pull_file.get('status')
            file_status = status_value if isinstance(status_value, str) else 'unknown'
            additions_value = pull_file.get('additions')
            additions = additions_value if isinstance(additions_value, int) else 0
            deletions_value = pull_file.get('deletions')
            deletions = deletions_value if isinstance(deletions_value, int) else 0
            patch_value = pull_file.get('patch')
            file_patch = (
                patch_value
                if isinstance(patch_value, str) and patch_value.strip() != ''
                else '[No textual patch content provided by GitHub for this file.]'
            )
            patch_length = len(file_patch)
            if (
                included_file_count > 0
                and used_patch_characters + patch_length > REVIEWER_PROMPT_MAX_PATCH_CHARACTERS
            ):
                diff_sections.append('... [diff context truncated by patch-size limit]')
                break

            diff_sections.append(
                '\n'.join(
                    [
                        f'File: {filename}',
                        f'Status: {file_status}',
                        f'Additions: {additions}',
                        f'Deletions: {deletions}',
                        'Patch:',
                        file_patch,
                    ]
                )
            )
            used_patch_characters += patch_length
            included_file_count += 1

        return '\n\n'.join(diff_sections), included_file_count

    def _build_reviewer_codex_prompt(self, normalized_event: NormalizedIngressEvent) -> str:
        pull_payload = self._github_client.fetch_pull_request(
            repository=normalized_event.repository,
            pull_number=normalized_event.entity_number,
        )
        pull_title = ''
        pull_body = ''
        pull_state = ''
        pull_changed_files = 0
        pull_additions = 0
        pull_deletions = 0
        pull_commits = 0
        pull_base_ref = ''
        pull_head_ref = ''
        if isinstance(pull_payload, dict):
            title_value = pull_payload.get('title')
            if isinstance(title_value, str):
                pull_title = title_value
            body_value = pull_payload.get('body')
            if isinstance(body_value, str):
                pull_body = body_value
            state_value = pull_payload.get('state')
            if isinstance(state_value, str):
                pull_state = state_value
            changed_files_value = pull_payload.get('changed_files')
            if isinstance(changed_files_value, int):
                pull_changed_files = changed_files_value
            additions_value = pull_payload.get('additions')
            if isinstance(additions_value, int):
                pull_additions = additions_value
            deletions_value = pull_payload.get('deletions')
            if isinstance(deletions_value, int):
                pull_deletions = deletions_value
            commits_value = pull_payload.get('commits')
            if isinstance(commits_value, int):
                pull_commits = commits_value
            base_payload = pull_payload.get('base')
            if isinstance(base_payload, dict):
                base_ref_value = base_payload.get('ref')
                if isinstance(base_ref_value, str):
                    pull_base_ref = base_ref_value
            head_payload = pull_payload.get('head')
            if isinstance(head_payload, dict):
                head_ref_value = head_payload.get('ref')
                if isinstance(head_ref_value, str):
                    pull_head_ref = head_ref_value

        ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
        is_review_thread_comment = bool(normalized_event.details.get('is_review_thread_comment', False))
        reviewer_diff_context, reviewer_diff_file_count = self._build_reviewer_diff_context(
            normalized_event,
        )
        if (
            ingress_event_type == IngressEventType.PR_REVIEW_COMMENT.value
            and is_review_thread_comment
        ):
            return _render_prompt_template(
                template_name='reviewer_codex_thread_reply',
                template_value=self._reviewer_codex_thread_reply_prompt_template,
                template_values={
                    'repository': normalized_event.repository,
                    'entity_key': normalized_event.entity_key,
                    'ingress_event_type': ingress_event_type,
                },
            )

        return _render_prompt_template(
            template_name='reviewer_codex_review',
            template_value=self._reviewer_codex_review_prompt_template,
            template_values={
                'repository': normalized_event.repository,
                'entity_key': normalized_event.entity_key,
                'ingress_event_type': ingress_event_type,
                'pull_title': pull_title,
                'pull_state': pull_state,
                'pull_base_ref': pull_base_ref,
                'pull_head_ref': pull_head_ref,
                'pull_changed_files': pull_changed_files,
                'pull_additions': pull_additions,
                'pull_deletions': pull_deletions,
                'pull_commits': pull_commits,
                'pull_body': pull_body,
                'reviewer_diff_file_count': reviewer_diff_file_count,
                'reviewer_diff_context': reviewer_diff_context,
            },
        )

    def _build_inline_review_submission_payload(
        self,
        normalized_event: NormalizedIngressEvent,
        reviewer_output: str,
    ) -> tuple[str, list[dict[str, object]]]:
        review_summary, parsed_comments = _parse_inline_review_payload(reviewer_output)
        pull_files = self._github_client.fetch_pull_request_files(
            repository=normalized_event.repository,
            pull_number=normalized_event.entity_number,
        )
        reviewable_lines_by_path = _collect_reviewable_lines_by_path(pull_files)
        validated_comments = _validate_inline_review_comments(
            comments_payload=parsed_comments,
            reviewable_lines_by_path=reviewable_lines_by_path,
        )
        return review_summary, validated_comments

    def _execute_reviewer_codex_task(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
    ) -> ExecutionResult | None:
        if self._codex_executor is None:
            return None

        task_id = (
            f"{current_job.job_id}:"
            f"{normalized_event.idempotency_key}:"
            'reviewer_follow_up'
        )
        try:
            return self._codex_executor.execute_task(
                task_id=task_id,
                prompt=self._build_reviewer_codex_prompt(normalized_event),
            )
        except Exception as error:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                summary='codex execution raised an exception',
                metadata=_build_transition_error_details(
                    error,
                    context={
                        'task_id': task_id,
                    },
                ),
            )

    def _execute_author_codex_task(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
    ) -> ExecutionResult | None:
        if self._codex_executor is None:
            return None

        task_id = (
            f"{current_job.job_id}:"
            f"{normalized_event.idempotency_key}:"
            'author_follow_up'
        )
        author_working_directory = self._resolve_author_codex_working_directory(normalized_event)
        try:
            return self._codex_executor.execute_task(
                task_id=task_id,
                prompt=self._build_author_codex_prompt(normalized_event),
                working_directory=author_working_directory,
            )
        except Exception as error:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                summary='codex execution raised an exception',
                metadata=_build_transition_error_details(
                    error,
                    context={
                        'task_id': task_id,
                    },
                ),
            )

    def _validate_mutating_lease(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        orchestrator: JobOrchestrator,
    ) -> tuple[JobRecord, bool]:
        lease_valid = orchestrator.validate_mutating_lease(
            job_id=current_job.job_id,
            expected_lease_epoch=current_job.lease_epoch,
            trace_id=normalized_event.trace_id,
        )
        latest_job = orchestrator.get_job(current_job.job_id)
        if latest_job is None:
            return current_job, lease_valid

        return latest_job, lease_valid

    def _create_comment_target_identity(
        self,
        normalized_event: NormalizedIngressEvent,
        comment_target: CommentTarget,
    ) -> str:
        if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
            thread_id = str(comment_target.thread_id or '')
            review_comment_id = int(comment_target.review_comment_id or 0)
            return (
                f"{normalized_event.repository}:"
                f"pr:{normalized_event.entity_number}:"
                f"thread:{thread_id}:{review_comment_id}"
            )

        if comment_target.target_type == CommentTargetType.PR:
            return f"{normalized_event.repository}:pr:{normalized_event.entity_number}"

        return f"{normalized_event.repository}:issue:{normalized_event.entity_number}"

    def _create_comment_target_outbox_id(
        self,
        normalized_event: NormalizedIngressEvent,
        action_type: OutboxActionType,
        target_identity: str,
    ) -> str:
        idempotency_hash = hashlib.sha1(
            normalized_event.idempotency_key.encode('utf-8')
        ).hexdigest()[:16]
        target_hash = hashlib.sha1(target_identity.encode('utf-8')).hexdigest()[:12]
        return (
            f"outbox_route:{idempotency_hash}:"
            f"{action_type.value}:{target_hash}"
        )

    def _build_comment_target_record(
        self,
        outbox_id: str,
        current_job: JobRecord,
        comment_target: CommentTarget,
        target_identity: str,
    ) -> CommentTargetRecord:
        return CommentTargetRecord(
            target_id=outbox_id,
            outbox_id=outbox_id,
            job_id=current_job.job_id,
            entity_key=current_job.entity_key,
            environment=current_job.environment,
            target_type=comment_target.target_type,
            target_identity=target_identity,
            issue_number=comment_target.issue_number,
            pr_number=comment_target.pr_number,
            thread_id=comment_target.thread_id,
            review_comment_id=comment_target.review_comment_id,
            path=comment_target.path,
            line=comment_target.line,
            side=comment_target.side,
            resolved_at=_utc_now(),
        )

    def _build_comment_target_intent(
        self,
        normalized_event: NormalizedIngressEvent,
        comment_target: CommentTarget,
        comment_body: str,
    ) -> tuple[OutboxActionType, str, dict[str, object]]:
        target_identity = self._create_comment_target_identity(normalized_event, comment_target)

        if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
            if comment_target.review_comment_id is None:
                raise ValueError('Missing review comment id for thread reply.')

            return (
                OutboxActionType.PR_REVIEW_REPLY,
                target_identity,
                {
                    'repository': normalized_event.repository,
                    'pull_number': normalized_event.entity_number,
                    'review_comment_id': comment_target.review_comment_id,
                    'body': comment_body,
                },
            )

        return (
            OutboxActionType.ISSUE_COMMENT,
            target_identity,
            {
                'repository': normalized_event.repository,
                'issue_number': normalized_event.entity_number,
                'body': comment_body,
            },
        )

    def _persist_comment_target_intent(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        comment_target: CommentTarget,
        comment_body: str,
        orchestrator: JobOrchestrator,
    ) -> tuple[OutboxRecord, OutboxActionType]:
        action_type, target_identity, payload = self._build_comment_target_intent(
            normalized_event=normalized_event,
            comment_target=comment_target,
            comment_body=comment_body,
        )
        idempotency_scope = build_canonical_idempotency_scope(
            entity_key=current_job.entity_key,
            action_type=action_type,
            target_identity=target_identity,
            payload=payload,
            policy_version=self._idempotency_policy_version,
        )
        idempotency_key = idempotency_scope.idempotency_key
        existing_outbox = orchestrator.get_outbox_entry_by_idempotency_scope(
            environment=current_job.environment,
            action_type=action_type,
            target_identity=target_identity,
            idempotency_key=idempotency_key,
            idempotency_schema_version=idempotency_scope.schema_version,
            idempotency_payload_hash=idempotency_scope.payload_hash,
            idempotency_policy_version_hash=idempotency_scope.policy_version_hash,
        )
        if existing_outbox is not None:
            existing_comment_target = orchestrator.get_comment_target_by_outbox_id(
                environment=current_job.environment,
                outbox_id=existing_outbox.outbox_id,
            )
            if existing_comment_target is None:
                orchestrator.append_comment_target(
                    self._build_comment_target_record(
                        outbox_id=existing_outbox.outbox_id,
                        current_job=current_job,
                        comment_target=comment_target,
                        target_identity=target_identity,
                    ),
                )
            return existing_outbox, action_type

        outbox_id = self._create_comment_target_outbox_id(
            normalized_event=normalized_event,
            action_type=action_type,
            target_identity=target_identity,
        )
        existing_outbox_by_outbox_id = orchestrator.get_outbox_entry_by_outbox_id(outbox_id)
        if existing_outbox_by_outbox_id is not None:
            existing_comment_target = orchestrator.get_comment_target_by_outbox_id(
                environment=current_job.environment,
                outbox_id=existing_outbox_by_outbox_id.outbox_id,
            )
            if existing_comment_target is None:
                orchestrator.append_comment_target(
                    self._build_comment_target_record(
                        outbox_id=existing_outbox_by_outbox_id.outbox_id,
                        current_job=current_job,
                        comment_target=comment_target,
                        target_identity=target_identity,
                    ),
                )
            return existing_outbox_by_outbox_id, action_type

        outbox_record = orchestrator.append_outbox_entry(
            OutboxWriteRequest(
                outbox_id=outbox_id,
                job_id=current_job.job_id,
                entity_key=current_job.entity_key,
                environment=current_job.environment,
                action_type=action_type,
                target_identity=target_identity,
                payload=payload,
                idempotency_key=idempotency_key,
                idempotency_policy_version=self._idempotency_policy_version,
                idempotency_schema_version=idempotency_scope.schema_version,
                idempotency_payload_hash=idempotency_scope.payload_hash,
                idempotency_policy_version_hash=idempotency_scope.policy_version_hash,
                job_lease_epoch=current_job.lease_epoch,
            ),
        )
        orchestrator.append_comment_target(
            self._build_comment_target_record(
                outbox_id=outbox_record.outbox_id,
                current_job=current_job,
                comment_target=comment_target,
                target_identity=target_identity,
            ),
        )
        return outbox_record, action_type

    def _dispatch_comment_target(
        self,
        normalized_event: NormalizedIngressEvent,
        comment_target: CommentTarget,
        comment_body: str,
    ) -> None:
        if comment_target.target_type == CommentTargetType.PR_REVIEW_THREAD:
            if comment_target.review_comment_id is None:
                raise ValueError('Missing review comment id for thread reply.')

            self._github_client.post_pull_review_comment_reply(
                repository=normalized_event.repository,
                pull_number=normalized_event.entity_number,
                review_comment_id=comment_target.review_comment_id,
                body=comment_body,
            )
            return

        self._github_client.post_issue_comment(
            repository=normalized_event.repository,
            issue_number=normalized_event.entity_number,
            body=comment_body,
        )

    def _deliver_comment_target(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        comment_target: CommentTarget,
        comment_body: str,
        orchestrator: JobOrchestrator,
    ) -> tuple[bool, dict[str, object] | None]:
        outbox_record, _ = self._persist_comment_target_intent(
            normalized_event=normalized_event,
            current_job=current_job,
            comment_target=comment_target,
            comment_body=comment_body,
            orchestrator=orchestrator,
        )
        if outbox_record.status == OutboxStatus.CONFIRMED:
            return True, None

        sent = orchestrator.mark_outbox_entry_sent(
            outbox_id=outbox_record.outbox_id,
            expected_lease_epoch=outbox_record.lease_epoch,
        )
        if sent is False:
            return (
                False,
                {
                    'error_type': 'outbox_send_failed',
                    'error_message': 'Failed to mark outbox entry as sent.',
                    'outbox_id': outbox_record.outbox_id,
                    'expected_lease_epoch': outbox_record.lease_epoch,
                },
            )

        sent_lease_epoch = outbox_record.lease_epoch + 1
        try:
            self._dispatch_comment_target(
                normalized_event=normalized_event,
                comment_target=comment_target,
                comment_body=comment_body,
            )
        except Exception as error:
            orchestrator.mark_outbox_entry_aborted(
                outbox_id=outbox_record.outbox_id,
                expected_lease_epoch=sent_lease_epoch,
                abort_reason=COMMENT_TARGET_OUTBOX_ABORT_REASON,
            )
            return (
                False,
                _build_transition_error_details(
                    error,
                    context={
                        'outbox_id': outbox_record.outbox_id,
                        'target_type': comment_target.target_type.value,
                        'repository': normalized_event.repository,
                        'entity_number': normalized_event.entity_number,
                    },
                ),
            )

        confirmed = orchestrator.mark_outbox_entry_confirmed(
            outbox_id=outbox_record.outbox_id,
            expected_lease_epoch=sent_lease_epoch,
        )
        if confirmed is False:
            return (
                False,
                {
                    'error_type': 'outbox_confirm_failed',
                    'error_message': 'Failed to mark outbox entry as confirmed.',
                    'outbox_id': outbox_record.outbox_id,
                    'expected_lease_epoch': sent_lease_epoch,
                },
            )

        return True, None

    def _execute_no_write_event(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        orchestrator: JobOrchestrator,
    ) -> JobRecord:
        if current_job.state == JobState.AWAITING_CONTEXT and _is_clarification_event(normalized_event):
            return orchestrator.transition_job(
                current_job.job_id,
                to_state=JobState.BLOCKED,
                reason=NO_WRITE_CLARIFICATION_REASON,
                trace_id=normalized_event.trace_id,
            )

        if current_job.state != JobState.READY_TO_EXECUTE:
            return current_job

        handles_feedback = (
            _is_reviewer_event(normalized_event, current_job)
            or _is_reviewer_thread_reply_event(normalized_event, current_job)
            or _is_author_feedback_event(normalized_event, current_job)
            or _is_supported_comment_event(normalized_event)
        )
        handles_ci = _is_author_ci_event(normalized_event, current_job)
        if handles_feedback is False and handles_ci is False:
            return current_job

        target_state = JobState.AWAITING_HUMAN_FEEDBACK
        target_reason = NO_WRITE_FEEDBACK_REASON
        if handles_ci:
            target_state = JobState.AWAITING_CI
            target_reason = NO_WRITE_CI_REASON

        no_write_executing_job = orchestrator.transition_job(
            current_job.job_id,
            to_state=JobState.EXECUTING,
            reason=NO_WRITE_EXECUTION_START_REASON,
            trace_id=normalized_event.trace_id,
        )
        return orchestrator.transition_job(
            no_write_executing_job.job_id,
            to_state=target_state,
            reason=target_reason,
            trace_id=normalized_event.trace_id,
        )

    def execute_for_event(
        self,
        normalized_event: NormalizedIngressEvent,
        current_job: JobRecord,
        orchestrator: JobOrchestrator,
    ) -> JobRecord:

        '''
        Create deterministic mention side-effect flow for eligible ready-to-execute jobs.

        Args:
        normalized_event (NormalizedIngressEvent): Normalized ingress event payload.
        current_job (JobRecord): Current durable job state.
        orchestrator (JobOrchestrator): Job orchestrator for deterministic transitions.

        Returns:
        JobRecord: Updated durable job state after mention side-effect handling.
        '''

        with get_tracer().start_as_current_span('ingress.mention_action.execute') as span:
            span.set_attribute('agent1.entity_key', normalized_event.entity_key)
            span.set_attribute('agent1.job_id', current_job.job_id)
            span.set_attribute('agent1.event_id', normalized_event.event_id)
            if current_job.mode != RuntimeMode.ACTIVE:
                return self._execute_no_write_event(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )

            if current_job.state == JobState.AWAITING_CONTEXT and _is_clarification_event(normalized_event):
                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                interaction_codex_result = self._execute_interaction_codex_task(
                    normalized_event=normalized_event,
                    current_job=current_job,
                )
                if interaction_codex_result is None:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=INTERACTION_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': 'interaction codex executor is not configured',
                            'error_type': 'RuntimeError',
                            'error_message': 'Interaction codex executor is not configured.',
                        },
                    )
                if interaction_codex_result.status == ExecutionStatus.FAILED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=INTERACTION_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': interaction_codex_result.summary,
                            **interaction_codex_result.metadata,
                        },
                    )
                if interaction_codex_result.status == ExecutionStatus.BLOCKED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=INTERACTION_CODEX_EXECUTION_BLOCKED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': interaction_codex_result.summary,
                            **interaction_codex_result.metadata,
                        },
                    )
                clarification_body = _extract_codex_stdout_text(interaction_codex_result)
                try:
                    self._github_client.post_issue_comment(
                        repository=normalized_event.repository,
                        issue_number=normalized_event.entity_number,
                        body=clarification_body,
                    )
                except Exception as error:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=CLARIFICATION_REQUEST_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details=_build_transition_error_details(
                            error,
                            context={
                                'repository': normalized_event.repository,
                                'entity_number': normalized_event.entity_number,
                                'action': 'post_issue_comment',
                            },
                        ),
                    )

                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=CLARIFICATION_REQUEST_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )

            if current_job.state != JobState.READY_TO_EXECUTE:
                return current_job
            if (
                _is_reviewer_event(normalized_event, current_job)
                or _is_reviewer_thread_reply_event(normalized_event, current_job)
            ):
                reviewer_codex_result = self._execute_reviewer_codex_task(normalized_event, current_job)
                if reviewer_codex_result is None:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=REVIEWER_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': 'reviewer codex executor is not configured',
                            'error_type': 'RuntimeError',
                            'error_message': 'Reviewer codex executor is not configured.',
                        },
                    )
                if reviewer_codex_result.status == ExecutionStatus.FAILED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=REVIEWER_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': reviewer_codex_result.summary,
                            **reviewer_codex_result.metadata,
                        },
                    )
                if reviewer_codex_result.status == ExecutionStatus.BLOCKED:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=REVIEWER_CODEX_EXECUTION_BLOCKED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': reviewer_codex_result.summary,
                            **reviewer_codex_result.metadata,
                        },
                    )

                try:
                    reviewer_body = _extract_codex_stdout_text(reviewer_codex_result)
                except Exception as error:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=REVIEWER_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': reviewer_codex_result.summary,
                            **reviewer_codex_result.metadata,
                            **_build_transition_error_details(error),
                        },
                    )

                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                reviewer_ingress_event_type = str(
                    normalized_event.details.get('ingress_event_type', ''),
                )
                try:
                    if reviewer_ingress_event_type == IngressEventType.PR_REVIEW_COMMENT.value:
                        comment_target = self._comment_router.route(normalized_event)
                        delivered, delivery_error_details = self._deliver_comment_target(
                            normalized_event=normalized_event,
                            current_job=current_job,
                            comment_target=comment_target,
                            comment_body=reviewer_body,
                            orchestrator=orchestrator,
                        )
                        if delivered is False:
                            return orchestrator.transition_job(
                                current_job.job_id,
                                to_state=JobState.BLOCKED,
                                reason=REVIEWER_RESPONSE_FAILED_REASON,
                                trace_id=normalized_event.trace_id,
                                transition_details=delivery_error_details,
                            )
                    else:
                        review_summary, inline_comments = self._build_inline_review_submission_payload(
                            normalized_event=normalized_event,
                            reviewer_output=reviewer_body,
                        )
                        self._github_client.submit_pull_request_review(
                            repository=normalized_event.repository,
                            pull_number=normalized_event.entity_number,
                            body=review_summary,
                            event='COMMENT',
                            comments=inline_comments,
                        )
                except CommentRoutingError as error:
                    orchestrator.emit_comment_routing_failure_alert(
                        environment=current_job.environment,
                        trace_id=normalized_event.trace_id,
                        job_id=current_job.job_id,
                        entity_key=current_job.entity_key,
                        error_message=str(error),
                    )
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=COMMENT_ROUTE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'error_type': error.__class__.__name__,
                            'error_message': str(error),
                            'repository': normalized_event.repository,
                            'entity_number': normalized_event.entity_number,
                            'ingress_event_type': reviewer_ingress_event_type,
                        },
                    )
                except Exception as error:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=REVIEWER_RESPONSE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details=_build_transition_error_details(
                            error,
                            context={
                                'repository': normalized_event.repository,
                                'entity_number': normalized_event.entity_number,
                                'action': (
                                    'post_pull_review_comment_reply'
                                    if reviewer_ingress_event_type
                                    == IngressEventType.PR_REVIEW_COMMENT.value
                                    else 'submit_pull_request_inline_review'
                                ),
                            },
                        ),
                    )

                reviewer_executing_job = orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.EXECUTING,
                    reason=REVIEWER_EXECUTION_START_REASON,
                    trace_id=normalized_event.trace_id,
                )
                return orchestrator.transition_job(
                    reviewer_executing_job.job_id,
                    to_state=JobState.AWAITING_HUMAN_FEEDBACK,
                    reason=REVIEWER_RESPONSE_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )
            if _is_author_feedback_event(normalized_event, current_job):
                author_codex_result = self._execute_author_codex_task(normalized_event, current_job)
                if author_codex_result is None:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': 'author codex executor is not configured',
                            'error_type': 'RuntimeError',
                            'error_message': 'Author codex executor is not configured.',
                        },
                    )
                if (
                    author_codex_result.status == ExecutionStatus.FAILED
                ):
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': author_codex_result.summary,
                            **author_codex_result.metadata,
                        },
                    )
                if (
                    author_codex_result.status == ExecutionStatus.BLOCKED
                ):
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_BLOCKED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': author_codex_result.summary,
                            **author_codex_result.metadata,
                        },
                    )

                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                try:
                    author_comment_body = _extract_codex_stdout_text(author_codex_result)
                except Exception as error:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': author_codex_result.summary,
                            **author_codex_result.metadata,
                            **_build_transition_error_details(error),
                        },
                    )
                try:
                    comment_target = self._comment_router.route(normalized_event)
                except CommentRoutingError as error:
                    orchestrator.emit_comment_routing_failure_alert(
                        environment=current_job.environment,
                        trace_id=normalized_event.trace_id,
                        job_id=current_job.job_id,
                        entity_key=current_job.entity_key,
                        error_message=str(error),
                    )
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=COMMENT_ROUTE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'error_type': error.__class__.__name__,
                            'error_message': str(error),
                            'repository': normalized_event.repository,
                            'entity_number': normalized_event.entity_number,
                            'ingress_event_type': str(
                                normalized_event.details.get('ingress_event_type', '')
                            ),
                        },
                    )

                delivered, delivery_error_details = self._deliver_comment_target(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    comment_target=comment_target,
                    comment_body=author_comment_body,
                    orchestrator=orchestrator,
                )
                if delivered is False:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_RESPONSE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details=delivery_error_details,
                    )

                author_executing_job = orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.EXECUTING,
                    reason=AUTHOR_EXECUTION_START_REASON,
                    trace_id=normalized_event.trace_id,
                )
                return orchestrator.transition_job(
                    author_executing_job.job_id,
                    to_state=JobState.AWAITING_HUMAN_FEEDBACK,
                    reason=AUTHOR_FEEDBACK_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )
            if _is_author_ci_event(normalized_event, current_job):
                author_codex_result = self._execute_author_codex_task(normalized_event, current_job)
                if author_codex_result is None:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': 'author codex executor is not configured',
                            'error_type': 'RuntimeError',
                            'error_message': 'Author codex executor is not configured.',
                        },
                    )
                if (
                    author_codex_result.status == ExecutionStatus.FAILED
                ):
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': author_codex_result.summary,
                            **author_codex_result.metadata,
                        },
                    )
                if (
                    author_codex_result.status == ExecutionStatus.BLOCKED
                ):
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_BLOCKED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': author_codex_result.summary,
                            **author_codex_result.metadata,
                        },
                    )

                current_job, lease_valid = self._validate_mutating_lease(
                    normalized_event=normalized_event,
                    current_job=current_job,
                    orchestrator=orchestrator,
                )
                if lease_valid is False:
                    return current_job

                try:
                    author_ci_body = _extract_codex_stdout_text(author_codex_result)
                except Exception as error:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_CODEX_EXECUTION_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details={
                            'codex_summary': author_codex_result.summary,
                            **author_codex_result.metadata,
                            **_build_transition_error_details(error),
                        },
                    )
                try:
                    self._github_client.post_issue_comment(
                        repository=normalized_event.repository,
                        issue_number=normalized_event.entity_number,
                        body=author_ci_body,
                    )
                except Exception as error:
                    return orchestrator.transition_job(
                        current_job.job_id,
                        to_state=JobState.BLOCKED,
                        reason=AUTHOR_RESPONSE_FAILED_REASON,
                        trace_id=normalized_event.trace_id,
                        transition_details=_build_transition_error_details(
                            error,
                            context={
                                'repository': normalized_event.repository,
                                'entity_number': normalized_event.entity_number,
                                'action': 'post_issue_comment',
                            },
                        ),
                    )

                author_executing_job = orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.EXECUTING,
                    reason=AUTHOR_EXECUTION_START_REASON,
                    trace_id=normalized_event.trace_id,
                )
                return orchestrator.transition_job(
                    author_executing_job.job_id,
                    to_state=JobState.AWAITING_CI,
                    reason=AUTHOR_CI_TRIAGE_POSTED_REASON,
                    trace_id=normalized_event.trace_id,
                )

            if _is_supported_comment_event(normalized_event) is False:
                return current_job

            try:
                comment_target = self._comment_router.route(normalized_event)
            except CommentRoutingError as error:
                orchestrator.emit_comment_routing_failure_alert(
                    environment=current_job.environment,
                    trace_id=normalized_event.trace_id,
                    job_id=current_job.job_id,
                    entity_key=current_job.entity_key,
                    error_message=str(error),
                )
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=COMMENT_ROUTE_FAILED_REASON,
                    trace_id=normalized_event.trace_id,
                    transition_details={
                        'error_type': error.__class__.__name__,
                        'error_message': str(error),
                        'repository': normalized_event.repository,
                        'entity_number': normalized_event.entity_number,
                        'ingress_event_type': str(normalized_event.details.get('ingress_event_type', '')),
                    },
                )

            current_job, lease_valid = self._validate_mutating_lease(
                normalized_event=normalized_event,
                current_job=current_job,
                orchestrator=orchestrator,
            )
            if lease_valid is False:
                return current_job

            interaction_codex_result = self._execute_interaction_codex_task(
                normalized_event=normalized_event,
                current_job=current_job,
            )
            if interaction_codex_result is None:
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=INTERACTION_CODEX_EXECUTION_FAILED_REASON,
                    trace_id=normalized_event.trace_id,
                    transition_details={
                        'codex_summary': 'interaction codex executor is not configured',
                        'error_type': 'RuntimeError',
                        'error_message': 'Interaction codex executor is not configured.',
                    },
                )
            if interaction_codex_result.status == ExecutionStatus.FAILED:
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=INTERACTION_CODEX_EXECUTION_FAILED_REASON,
                    trace_id=normalized_event.trace_id,
                    transition_details={
                        'codex_summary': interaction_codex_result.summary,
                        **interaction_codex_result.metadata,
                    },
                )
            if interaction_codex_result.status == ExecutionStatus.BLOCKED:
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=INTERACTION_CODEX_EXECUTION_BLOCKED_REASON,
                    trace_id=normalized_event.trace_id,
                    transition_details={
                        'codex_summary': interaction_codex_result.summary,
                        **interaction_codex_result.metadata,
                    },
                )
            try:
                comment_body = _extract_codex_stdout_text(interaction_codex_result)
            except Exception as error:
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=INTERACTION_CODEX_EXECUTION_FAILED_REASON,
                    trace_id=normalized_event.trace_id,
                    transition_details={
                        'codex_summary': interaction_codex_result.summary,
                        **interaction_codex_result.metadata,
                        **_build_transition_error_details(error),
                    },
                )
            delivered, delivery_error_details = self._deliver_comment_target(
                normalized_event=normalized_event,
                current_job=current_job,
                comment_target=comment_target,
                comment_body=comment_body,
                orchestrator=orchestrator,
            )
            if delivered is False:
                return orchestrator.transition_job(
                    current_job.job_id,
                    to_state=JobState.BLOCKED,
                    reason=MENTION_RESPONSE_FAILED_REASON,
                    trace_id=normalized_event.trace_id,
                    transition_details=delivery_error_details,
                )

            executing_job = orchestrator.transition_job(
                current_job.job_id,
                to_state=JobState.EXECUTING,
                reason=MENTION_EXECUTION_START_REASON,
                trace_id=normalized_event.trace_id,
            )
            return orchestrator.transition_job(
                executing_job.job_id,
                to_state=JobState.AWAITING_HUMAN_FEEDBACK,
                reason=MENTION_RESPONSE_POSTED_REASON,
                trace_id=normalized_event.trace_id,
            )


__all__ = ['MentionActionExecutor']
