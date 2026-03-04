import json
import hashlib
from pathlib import Path

import pytest

from agent1.core.control_loader import CONTROL_FILE_NAME
from agent1.core.control_loader import POLICY_PERMISSION_MATRIX_FILE_NAME
from agent1.core.control_loader import POLICY_PROTECTED_APPROVAL_FILE_NAME
from agent1.core.control_loader import ControlValidationError
from agent1.core.control_loader import load_control_bundle


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding='utf-8')


def _create_permission_matrix_payload() -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for component in ['api', 'worker', 'watcher', 'dashboard', 'ci']:
        for environment in ['dev', 'prod', 'ci']:
            entries.append(
                {
                    'component': component,
                    'environment': environment,
                    'permissions': [f'{component}_read', f'{component}_write'],
                }
            )

    return {
        'entries': entries,
        'persistence_roles': {
            'migrator': ['schema_read', 'schema_write'],
            'runtime': ['data_read', 'data_write'],
            'readonly_analytics': ['data_read'],
        },
    }


def _sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_protected_mutation_approval_payload(root: Path) -> dict[str, object]:
    protected_relative_paths = (
        'policies/default.json',
        'policies/permission-matrix.json',
        'runtime/default.json',
    )
    protected_files = [
        {
            'path': relative_path,
            'sha256': _sha256_hex(root / relative_path),
        }
        for relative_path in protected_relative_paths
    ]
    return {
        'version': '0.1.0',
        'active_snapshot': {
            'approval_id': 'approval_controls_001',
            'change_ticket': 'controls-baseline',
            'approved_by': ['controls-owner'],
            'approved_at': '2026-03-01T00:00:00Z',
            'reason': 'Baseline protected approval for policy and guardrail controls.',
            'protected_files': protected_files,
        },
        'audit_trail': [
            {
                'event_id': 'approval_controls_001_event_approved',
                'approval_id': 'approval_controls_001',
                'decision': 'approved',
                'recorded_at': '2026-03-01T00:00:00Z',
                'recorded_by': 'controls-owner',
                'note': 'Initial protected approval event.',
            }
        ],
    }


def _create_valid_controls(root: Path) -> None:
    _write_json(
        root / 'prompts' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'templates': {
                'issue_assignment': {
                    'system_prompt': 'You are Agent1.',
                    'task_prompt': 'Handle the assigned issue.',
                }
            },
        },
    )
    _write_json(
        root / 'policies' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'repo_scope': ['Vaquum/Agent1'],
            'agent_actor': 'runtime-agent-user',
            'ignored_actors': [],
            'ignored_actor_suffixes': ['[bot]'],
            'deny_git_commands': ['git push --force'],
            'allowed_git_mutation_commands': ['git add', 'git commit', 'git push'],
            'branch_mutation_patterns_by_environment': {
                'dev': ['sandbox/*'],
                'prod': ['release/*'],
                'ci': ['sandbox/*', 'ci/*'],
            },
            'enforce_read_write_credential_split': True,
            'default_deny_github_capabilities': True,
            'fail_closed_policy_resolution': True,
            'mutating_credential_owner_by_environment': {
                'dev': 'runtime-agent-user',
                'prod': 'runtime-agent-user',
                'ci': 'runtime-agent-user',
            },
            'github_capabilities': {
                'read_notifications': True,
                'read_pr_timeline': True,
                'read_pr_check_runs': True,
                'read_issue': True,
                'read_pull_request': True,
                'write_issue_comment': True,
                'write_pr_review_reply': True,
            },
            'rules': [],
        },
    )
    _write_json(
        root / 'policies' / POLICY_PERMISSION_MATRIX_FILE_NAME,
        _create_permission_matrix_payload(),
    )
    _write_json(
        root / 'styles' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'coding_style': 'clean',
            'communication_style': 'concise',
        },
    )
    _write_json(
        root / 'commenting' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'require_review_thread_reply': True,
            'allow_top_level_pr_fallback': False,
            'issue_comment_mode': 'top_level_only',
        },
    )
    _write_json(
        root / 'jobs' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'rules': [
                {
                    'job_kind': 'issue',
                    'terminal_states': ['completed', 'blocked'],
                }
            ],
        },
    )
    _write_json(
        root / 'runtime' / CONTROL_FILE_NAME,
        {
            'version': '0.1.0',
            'mode': 'active',
            'active_repositories': ['Vaquum/Agent1'],
            'require_sandbox_scope_for_dev_active': True,
            'sandbox_label': 'agent1-sandbox',
            'sandbox_branch_prefix': 'sandbox/',
            'poll_interval_seconds': 30,
            'watch_interval_seconds': 30,
            'max_retry_attempts': 5,
            'retention_policy': {
                'entries': [
                    {
                        'artifact_type': 'logs',
                        'environment': 'dev',
                        'retention_days': 14,
                    },
                    {
                        'artifact_type': 'logs',
                        'environment': 'prod',
                        'retention_days': 30,
                    },
                    {
                        'artifact_type': 'logs',
                        'environment': 'ci',
                        'retention_days': 14,
                    },
                    {
                        'artifact_type': 'traces',
                        'environment': 'dev',
                        'retention_days': 14,
                    },
                    {
                        'artifact_type': 'traces',
                        'environment': 'prod',
                        'retention_days': 30,
                    },
                    {
                        'artifact_type': 'traces',
                        'environment': 'ci',
                        'retention_days': 14,
                    },
                    {
                        'artifact_type': 'test_artifacts',
                        'environment': 'dev',
                        'retention_days': 14,
                    },
                    {
                        'artifact_type': 'test_artifacts',
                        'environment': 'prod',
                        'retention_days': 30,
                    },
                    {
                        'artifact_type': 'test_artifacts',
                        'environment': 'ci',
                        'retention_days': 14,
                    },
                ]
            },
            'rollout_policy': {
                'health_signals': [
                    {
                        'signal_id': 'side_effect_success_rate',
                        'description': 'Mutating side-effect success rate health signal.',
                    },
                    {
                        'signal_id': 'lease_violation_rate',
                        'description': 'Lease-violation health signal.',
                    },
                ],
                'stages': [
                    {
                        'stage_id': 'dev_shadow',
                        'description': 'Shadow stage',
                        'required_health_signals': ['lease_violation_rate'],
                    },
                    {
                        'stage_id': 'dev_active',
                        'description': 'Active stage',
                        'required_health_signals': [
                            'side_effect_success_rate',
                            'lease_violation_rate',
                        ],
                    },
                ],
            },
            'stop_the_line_policy': {
                'rules': [
                    {
                        'signal_id': 'error_rate',
                        'comparator': 'gte',
                        'threshold': 0.05,
                        'evaluation_window_minutes': 15,
                    },
                    {
                        'signal_id': 'lease_violation_rate',
                        'comparator': 'gte',
                        'threshold': 0.01,
                        'evaluation_window_minutes': 15,
                    },
                ]
            },
            'release_promotion_policy': {
                'preconditions': [
                    {
                        'precondition_id': 'operational_readiness_gate_passed',
                        'description': 'Operational-readiness validation gate passes.',
                    },
                    {
                        'precondition_id': 'stop_the_line_clear',
                        'description': 'No active stop-the-line breach remains.',
                    },
                ]
            },
        },
    )
    _write_json(
        root / 'policies' / POLICY_PROTECTED_APPROVAL_FILE_NAME,
        _create_protected_mutation_approval_payload(root),
    )


def test_load_control_bundle_parses_valid_controls(tmp_path: Path) -> None:
    _create_valid_controls(tmp_path)
    bundle = load_control_bundle(tmp_path)

    assert bundle.runtime.poll_interval_seconds == 30
    assert bundle.runtime.active_repositories == ['Vaquum/Agent1']
    assert bundle.runtime.require_sandbox_scope_for_dev_active is True
    assert bundle.commenting.require_review_thread_reply is True
    assert bundle.policies.agent_actor == 'runtime-agent-user'
    assert bundle.policies.ignored_actor_suffixes == ['[bot]']
    assert bundle.policies.allowed_git_mutation_commands == ['git add', 'git commit', 'git push']
    assert len(bundle.policies.permission_matrix.entries) == 15
    assert bundle.policies.permission_matrix.persistence_roles.runtime == ['data_read', 'data_write']
    assert bundle.policies.protected_mutation_approval.active_snapshot.approval_id == (
        'approval_controls_001'
    )
    assert bundle.runtime.rollout_policy.stages[0].stage_id == 'dev_shadow'
    assert bundle.runtime.rollout_policy.stages[1].required_health_signals == [
        'side_effect_success_rate',
        'lease_violation_rate',
    ]
    assert len(bundle.runtime.retention_policy.entries) == 9
    assert bundle.runtime.stop_the_line_policy.rules[0].signal_id == 'error_rate'
    assert bundle.runtime.stop_the_line_policy.rules[1].threshold == 0.01
    assert bundle.runtime.release_promotion_policy.preconditions[0].precondition_id == (
        'operational_readiness_gate_passed'
    )
    assert bundle.runtime.release_promotion_policy.preconditions[1].precondition_id == (
        'stop_the_line_clear'
    )


def test_load_control_bundle_fails_when_control_file_missing(tmp_path: Path) -> None:
    _create_valid_controls(tmp_path)
    (tmp_path / 'runtime' / CONTROL_FILE_NAME).unlink()

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_permission_matrix_file_missing(tmp_path: Path) -> None:
    _create_valid_controls(tmp_path)
    (tmp_path / 'policies' / POLICY_PERMISSION_MATRIX_FILE_NAME).unlink()

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_protected_approval_file_missing(tmp_path: Path) -> None:
    _create_valid_controls(tmp_path)
    (tmp_path / 'policies' / POLICY_PROTECTED_APPROVAL_FILE_NAME).unlink()

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_rollout_stage_references_unknown_signal(
    tmp_path: Path,
) -> None:
    _create_valid_controls(tmp_path)
    runtime_path = tmp_path / 'runtime' / CONTROL_FILE_NAME
    runtime_payload = json.loads(runtime_path.read_text(encoding='utf-8'))
    runtime_payload['rollout_policy']['stages'][0]['required_health_signals'] = ['unknown_signal']
    runtime_path.write_text(json.dumps(runtime_payload), encoding='utf-8')

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_stop_the_line_policy_has_duplicate_signal_rules(
    tmp_path: Path,
) -> None:
    _create_valid_controls(tmp_path)
    runtime_path = tmp_path / 'runtime' / CONTROL_FILE_NAME
    runtime_payload = json.loads(runtime_path.read_text(encoding='utf-8'))
    runtime_payload['stop_the_line_policy']['rules'][1]['signal_id'] = 'error_rate'
    runtime_path.write_text(json.dumps(runtime_payload), encoding='utf-8')

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_release_promotion_policy_has_duplicate_preconditions(
    tmp_path: Path,
) -> None:
    _create_valid_controls(tmp_path)
    runtime_path = tmp_path / 'runtime' / CONTROL_FILE_NAME
    runtime_payload = json.loads(runtime_path.read_text(encoding='utf-8'))
    runtime_payload['release_promotion_policy']['preconditions'][1]['precondition_id'] = (
        'operational_readiness_gate_passed'
    )
    runtime_path.write_text(json.dumps(runtime_payload), encoding='utf-8')

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_permission_matrix_is_missing_component_environment_pair(
    tmp_path: Path,
) -> None:
    _create_valid_controls(tmp_path)
    permission_matrix_path = tmp_path / 'policies' / POLICY_PERMISSION_MATRIX_FILE_NAME
    permission_matrix_payload = json.loads(permission_matrix_path.read_text(encoding='utf-8'))
    permission_matrix_payload['entries'] = [
        entry
        for entry in permission_matrix_payload['entries']
        if not (
            entry.get('component') == 'worker'
            and entry.get('environment') == 'prod'
        )
    ]
    permission_matrix_path.write_text(json.dumps(permission_matrix_payload), encoding='utf-8')

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_retention_policy_is_missing_artifact_environment_pair(
    tmp_path: Path,
) -> None:
    _create_valid_controls(tmp_path)
    runtime_path = tmp_path / 'runtime' / CONTROL_FILE_NAME
    runtime_payload = json.loads(runtime_path.read_text(encoding='utf-8'))
    runtime_payload['retention_policy']['entries'] = [
        entry
        for entry in runtime_payload['retention_policy']['entries']
        if not (
            entry.get('artifact_type') == 'logs'
            and entry.get('environment') == 'prod'
        )
    ]
    runtime_path.write_text(json.dumps(runtime_payload), encoding='utf-8')

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_protected_approval_hash_mismatches(tmp_path: Path) -> None:
    _create_valid_controls(tmp_path)
    protected_approval_path = tmp_path / 'policies' / POLICY_PROTECTED_APPROVAL_FILE_NAME
    protected_approval_payload = json.loads(protected_approval_path.read_text(encoding='utf-8'))
    protected_approval_payload['active_snapshot']['protected_files'][0]['sha256'] = '0' * 64
    protected_approval_path.write_text(json.dumps(protected_approval_payload), encoding='utf-8')

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)


def test_load_control_bundle_fails_when_protected_approval_latest_audit_decision_is_revoked(
    tmp_path: Path,
) -> None:
    _create_valid_controls(tmp_path)
    protected_approval_path = tmp_path / 'policies' / POLICY_PROTECTED_APPROVAL_FILE_NAME
    protected_approval_payload = json.loads(protected_approval_path.read_text(encoding='utf-8'))
    protected_approval_payload['audit_trail'].append(
        {
            'event_id': 'approval_controls_001_event_revoked',
            'approval_id': 'approval_controls_001',
            'decision': 'revoked',
            'recorded_at': '2026-03-01T00:01:00Z',
            'recorded_by': 'controls-owner',
            'note': 'Revoked approval to validate fail-closed behavior.',
        }
    )
    protected_approval_path.write_text(json.dumps(protected_approval_payload), encoding='utf-8')

    with pytest.raises(ControlValidationError):
        load_control_bundle(tmp_path)
