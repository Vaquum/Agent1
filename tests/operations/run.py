from __future__ import annotations

import json
from pathlib import Path

REQUIRED_RUNBOOK_RELATIVE_PATHS: tuple[str, ...] = (
    'docs/Developer/runbooks/deploy-and-rollback.md',
    'docs/Developer/runbooks/migration-failback.md',
    'docs/Developer/runbooks/lease-and-idempotency-incidents.md',
    'docs/Developer/runbooks/review-thread-routing-failures.md',
    'docs/Developer/runbooks/github-rate-limit-and-token-failures.md',
)
REQUIRED_READINESS_HEADINGS: tuple[str, ...] = (
    '## Last Updated',
    '## Runbook Currency Confirmation',
    '## Alert Routing Validation Evidence',
    '## Rollback Rehearsal Evidence',
)
SERVICE_LEVEL_POLICY_RELATIVE_PATH = 'docs/Developer/service-level-policy.md'
REQUIRED_SERVICE_LEVEL_HEADINGS: tuple[str, ...] = (
    '## Last Updated',
    '## Service Level Objectives',
    '## Error Budget Policy',
    '## Release Freeze And Recovery Rules',
    '## Exception Approval Path',
)
REQUIRED_SERVICE_LEVEL_METRICS: tuple[str, ...] = (
    'trigger-to-first-action latency',
    'side-effect success rate',
    'duplicate side-effect rate',
    'mean-time-to-recovery',
)
ALERT_ROUTING_MATRIX_RELATIVE_PATH = 'docs/Developer/alert-routing-matrix.json'
REQUIRED_ALERT_SEVERITIES: tuple[str, ...] = (
    'sev1',
    'sev2',
)
REQUIRED_ALERT_NAMES: tuple[str, ...] = (
    'lease_violations',
    'duplicate_side_effect_anomalies',
    'comment_routing_failures',
    'outbox_backlog_growth',
    'elevated_failed_transition_rates',
)
INCIDENT_RESPONSE_POLICY_RELATIVE_PATH = 'docs/Developer/incident-response-policy.md'
REQUIRED_INCIDENT_HEADINGS: tuple[str, ...] = (
    '## Last Updated',
    '## Severity Levels And Ownership Routing',
    '## Response-Time Targets',
    '## Incident Commander And Communication Cadence',
    '## Post-Incident Review And Corrective Action',
    '## Corrective Action Feedback Loop',
)
RELEASE_CONTROL_RELATIVE_PATH = 'docs/Developer/release-control.json'
RELEASE_CONTROL_REQUIRED_STRING_FIELDS: tuple[str, ...] = (
    'last_updated',
    'freeze_reason',
)
RELEASE_CONTROL_REQUIRED_BOOLEAN_FIELDS: tuple[str, ...] = (
    'release_frozen',
    'exception_approved',
)
ROLLBACK_REHEARSAL_LOG_RELATIVE_PATH = 'docs/Developer/rollback-rehearsal-log.md'
REQUIRED_ROLLBACK_REHEARSAL_HEADINGS: tuple[str, ...] = (
    '# Rollback Rehearsal Log',
    '## Latest Rehearsal',
    '## Rehearsal History',
)
DEPLOYMENT_ENVIRONMENT_CONTRACT_RELATIVE_PATH = 'docs/Developer/deployment-environment-contract.md'
REQUIRED_DEPLOYMENT_CONTRACT_HEADINGS: tuple[str, ...] = (
    '# Deployment Environment Contract',
    '## Overview',
    '## Backend Environment Variables',
    '## Frontend Environment Variables',
    '## Release Migration Automation',
)
REQUIRED_DEPLOYMENT_ARTIFACT_PATHS: tuple[str, ...] = (
    '.dockerignore',
    'render.yaml',
    'apps/backend/Dockerfile',
    'apps/backend/docker/entrypoint.sh',
    'apps/frontend/Dockerfile',
)
REQUIRED_RENDER_BLUEPRINT_SNIPPETS: tuple[str, ...] = (
    'name: agent1-backend',
    'name: agent1-frontend',
    'dockerfilePath: ./apps/backend/Dockerfile',
    'dockerfilePath: ./apps/frontend/Dockerfile',
    'preDeployCommand: cd /app/apps/backend && alembic upgrade head',
    'DATABASE_URL',
    'GITHUB_TOKEN',
    'VITE_AGENT1_API_BASE_URL',
)
PLACEHOLDER_TOKENS: tuple[str, ...] = (
    'todo',
    'tbd',
    'placeholder',
)


def _get_repo_root() -> Path:

    '''
    Create repository root path from operations runner module location.

    Returns:
    Path: Repository root path.
    '''

    return Path(__file__).resolve().parents[2]


def _read_text(path: Path) -> str:

    '''
    Create text payload loaded from markdown artifact path.

    Args:
    path (Path): Artifact path to load.

    Returns:
    str: Decoded UTF-8 text payload.
    '''

    return path.read_text(encoding='utf-8')


def _read_json(path: Path) -> object:

    '''
    Create JSON payload loaded from artifact path.

    Args:
    path (Path): JSON artifact path to load.

    Returns:
    object: Decoded JSON payload.
    '''

    return json.loads(_read_text(path))


def _extract_markdown_sections(markdown_text: str) -> dict[str, str]:

    '''
    Create markdown section map keyed by second-level heading line.

    Args:
    markdown_text (str): Markdown payload to parse.

    Returns:
    dict[str, str]: Heading to section-content mapping.
    '''

    section_map: dict[str, list[str]] = {}
    current_heading: str | None = None
    for line in markdown_text.splitlines():
        if line.startswith('## '):
            current_heading = line.strip()
            section_map[current_heading] = []
            continue

        if current_heading is not None:
            section_map[current_heading].append(line)

    return {
        heading: '\n'.join(content_lines).strip()
        for heading, content_lines in section_map.items()
    }


def _contains_placeholder(section_text: str) -> bool:

    '''
    Compute placeholder-token presence for readiness section text.

    Args:
    section_text (str): Section content text.

    Returns:
    bool: True when placeholder tokens are present.
    '''

    normalized_text = section_text.lower()
    return any(token in normalized_text for token in PLACEHOLDER_TOKENS)


def _validate_runbook_set(repo_root: Path) -> list[str]:

    '''
    Create runbook validation findings for required operational runbook set.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    for relative_path in REQUIRED_RUNBOOK_RELATIVE_PATHS:
        runbook_path = repo_root / relative_path
        if not runbook_path.exists():
            findings.append(f'Missing required runbook: {relative_path}.')
            continue

        markdown_text = _read_text(runbook_path).strip()
        if markdown_text == '':
            findings.append(f'Required runbook is empty: {relative_path}.')
            continue

        if len(markdown_text.splitlines()) < 8:
            findings.append(f'Required runbook is too short: {relative_path}.')

    return findings


def _validate_operational_readiness_evidence(repo_root: Path) -> list[str]:

    '''
    Create operational-readiness evidence validation findings.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    readiness_path = repo_root / 'docs/Developer/operational-readiness.md'
    if not readiness_path.exists():
        findings.append('Missing required readiness artifact: docs/Developer/operational-readiness.md.')
        return findings

    markdown_text = _read_text(readiness_path)
    section_map = _extract_markdown_sections(markdown_text)
    for required_heading in REQUIRED_READINESS_HEADINGS:
        section_text = section_map.get(required_heading)
        if section_text is None:
            findings.append(f'Missing readiness heading: {required_heading}.')
            continue

        if section_text.strip() == '':
            findings.append(f'Empty readiness section: {required_heading}.')
            continue

        if _contains_placeholder(section_text):
            findings.append(f'Placeholder token detected in section: {required_heading}.')

    for relative_path in REQUIRED_RUNBOOK_RELATIVE_PATHS:
        runbook_filename = Path(relative_path).name
        if runbook_filename not in markdown_text:
            findings.append(
                'Readiness artifact does not reference required runbook '
                f'{runbook_filename}.',
            )

    return findings


def _validate_service_level_policy(repo_root: Path) -> list[str]:

    '''
    Create service-level policy validation findings for Phase 11 gating.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    policy_path = repo_root / SERVICE_LEVEL_POLICY_RELATIVE_PATH
    if not policy_path.exists():
        findings.append(f'Missing required service-level policy: {SERVICE_LEVEL_POLICY_RELATIVE_PATH}.')
        return findings

    markdown_text = _read_text(policy_path)
    section_map = _extract_markdown_sections(markdown_text)
    for required_heading in REQUIRED_SERVICE_LEVEL_HEADINGS:
        section_text = section_map.get(required_heading)
        if section_text is None:
            findings.append(f'Missing service-level heading: {required_heading}.')
            continue

        if section_text.strip() == '':
            findings.append(f'Empty service-level section: {required_heading}.')
            continue

        if _contains_placeholder(section_text):
            findings.append(f'Placeholder token detected in section: {required_heading}.')

    normalized_policy_text = markdown_text.lower()
    for metric_name in REQUIRED_SERVICE_LEVEL_METRICS:
        if metric_name not in normalized_policy_text:
            findings.append(f'Service-level policy is missing metric definition: {metric_name}.')

    if 'error budget' not in normalized_policy_text:
        findings.append('Service-level policy is missing error budget language.')

    if 'freeze' not in normalized_policy_text:
        findings.append('Service-level policy is missing release freeze rules.')

    return findings


def _validate_alert_routing_matrix(repo_root: Path) -> list[str]:

    '''
    Create alert-routing matrix validation findings for escalation readiness.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    matrix_path = repo_root / ALERT_ROUTING_MATRIX_RELATIVE_PATH
    if not matrix_path.exists():
        findings.append(f'Missing alert-routing matrix: {ALERT_ROUTING_MATRIX_RELATIVE_PATH}.')
        return findings

    try:
        payload = _read_json(matrix_path)
    except ValueError as error:
        findings.append(f'Alert-routing matrix is invalid JSON: {error}.')
        return findings

    if not isinstance(payload, dict):
        findings.append('Alert-routing matrix payload must be an object.')
        return findings

    severities = payload.get('severities')
    if not isinstance(severities, list):
        findings.append('Alert-routing matrix is missing severities list.')
        return findings

    seen_severities: set[str] = set()
    seen_alert_names: set[str] = set()
    for severity_payload in severities:
        if not isinstance(severity_payload, dict):
            findings.append('Alert-routing severity entry must be an object.')
            continue

        severity_name = severity_payload.get('severity')
        if not isinstance(severity_name, str) or severity_name.strip() == '':
            findings.append('Alert-routing severity entry is missing severity name.')
            continue

        normalized_severity_name = severity_name.strip().lower()
        seen_severities.add(normalized_severity_name)
        alerts = severity_payload.get('alerts')
        if not isinstance(alerts, list) or len(alerts) == 0:
            findings.append(f'Alert-routing severity has no alerts: {severity_name}.')
            continue

        for alert_payload in alerts:
            if not isinstance(alert_payload, dict):
                findings.append(f'Alert entry for {severity_name} must be an object.')
                continue

            alert_name = alert_payload.get('name')
            runbook_path = alert_payload.get('runbook')
            include_trace_id = alert_payload.get('include_trace_id')
            include_job_id = alert_payload.get('include_job_id')
            if not isinstance(alert_name, str) or alert_name.strip() == '':
                findings.append(f'Alert entry for {severity_name} is missing name.')
                continue

            normalized_alert_name = alert_name.strip().lower()
            seen_alert_names.add(normalized_alert_name)
            if not isinstance(runbook_path, str) or runbook_path.strip() == '':
                findings.append(f'Alert {alert_name} is missing runbook link.')
            else:
                absolute_runbook_path = repo_root / runbook_path.strip()
                if not absolute_runbook_path.exists():
                    findings.append(
                        f'Alert {alert_name} references missing runbook path {runbook_path}.',
                    )

            if include_trace_id is not True:
                findings.append(f'Alert {alert_name} must require trace_id in payload.')
            if include_job_id is not True:
                findings.append(f'Alert {alert_name} must require job_id in payload.')

    for severity_name in REQUIRED_ALERT_SEVERITIES:
        if severity_name not in seen_severities:
            findings.append(f'Alert-routing matrix is missing required severity: {severity_name}.')

    for alert_name in REQUIRED_ALERT_NAMES:
        if alert_name not in seen_alert_names:
            findings.append(f'Alert-routing matrix is missing required alert: {alert_name}.')

    return findings


def _validate_incident_response_policy(repo_root: Path) -> list[str]:

    '''
    Create incident-response policy validation findings for lifecycle readiness.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    policy_path = repo_root / INCIDENT_RESPONSE_POLICY_RELATIVE_PATH
    if not policy_path.exists():
        findings.append(f'Missing incident-response policy: {INCIDENT_RESPONSE_POLICY_RELATIVE_PATH}.')
        return findings

    markdown_text = _read_text(policy_path)
    section_map = _extract_markdown_sections(markdown_text)
    for required_heading in REQUIRED_INCIDENT_HEADINGS:
        section_text = section_map.get(required_heading)
        if section_text is None:
            findings.append(f'Missing incident-response heading: {required_heading}.')
            continue

        if section_text.strip() == '':
            findings.append(f'Empty incident-response section: {required_heading}.')
            continue

        if _contains_placeholder(section_text):
            findings.append(f'Placeholder token detected in section: {required_heading}.')

    normalized_policy_text = markdown_text.lower()
    if 'sev1' not in normalized_policy_text:
        findings.append('Incident-response policy is missing Sev1 coverage.')
    if 'sev2' not in normalized_policy_text:
        findings.append('Incident-response policy is missing Sev2 coverage.')
    if 'due date' not in normalized_policy_text:
        findings.append('Incident-response policy is missing corrective-action due date requirement.')
    if 'tests' not in normalized_policy_text:
        findings.append('Incident-response policy is missing tests feedback-loop requirement.')
    if 'controls' not in normalized_policy_text:
        findings.append('Incident-response policy is missing controls feedback-loop requirement.')
    if 'runbooks' not in normalized_policy_text:
        findings.append('Incident-response policy is missing runbooks feedback-loop requirement.')

    return findings


def _validate_release_control(repo_root: Path) -> list[str]:

    '''
    Create release-control validation findings for freeze and exception enforcement.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    release_control_path = repo_root / RELEASE_CONTROL_RELATIVE_PATH
    if not release_control_path.exists():
        findings.append(f'Missing release-control artifact: {RELEASE_CONTROL_RELATIVE_PATH}.')
        return findings

    try:
        payload = _read_json(release_control_path)
    except ValueError as error:
        findings.append(f'Release-control artifact is invalid JSON: {error}.')
        return findings

    if not isinstance(payload, dict):
        findings.append('Release-control payload must be an object.')
        return findings

    for field_name in RELEASE_CONTROL_REQUIRED_BOOLEAN_FIELDS:
        value = payload.get(field_name)
        if not isinstance(value, bool):
            findings.append(f'Release-control field {field_name} must be a boolean.')

    for field_name in RELEASE_CONTROL_REQUIRED_STRING_FIELDS:
        value = payload.get(field_name)
        if not isinstance(value, str) or value.strip() == '':
            findings.append(f'Release-control field {field_name} must be a non-empty string.')
            continue

        if _contains_placeholder(value):
            findings.append(f'Release-control field {field_name} contains placeholder content.')

    approvers = payload.get('exception_approvers')
    if not isinstance(approvers, list):
        findings.append('Release-control field exception_approvers must be a list.')
        approver_names: list[str] = []
    else:
        approver_names = []
        for approver in approvers:
            if not isinstance(approver, str) or approver.strip() == '':
                findings.append('Release-control exception approvers must be non-empty strings.')
                continue

            approver_names.append(approver.strip())

    mitigation_plan = payload.get('exception_mitigation_plan')
    if not isinstance(mitigation_plan, str):
        findings.append('Release-control field exception_mitigation_plan must be a string.')
        normalized_mitigation_plan = ''
    else:
        normalized_mitigation_plan = mitigation_plan.strip()
        if _contains_placeholder(normalized_mitigation_plan):
            findings.append('Release-control mitigation plan contains placeholder content.')

    release_frozen = payload.get('release_frozen')
    exception_approved = payload.get('exception_approved')
    if isinstance(release_frozen, bool) and isinstance(exception_approved, bool):
        if release_frozen and not exception_approved:
            findings.append(
                'Release-control indicates release_frozen without approved exception.',
            )

        if exception_approved:
            if len(approver_names) == 0:
                findings.append('Approved release exception requires at least one approver.')
            if normalized_mitigation_plan == '':
                findings.append('Approved release exception requires mitigation plan content.')

    return findings


def _validate_rollback_rehearsal_log(repo_root: Path) -> list[str]:

    '''
    Create rollback rehearsal evidence validation findings.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    rehearsal_log_path = repo_root / ROLLBACK_REHEARSAL_LOG_RELATIVE_PATH
    if not rehearsal_log_path.exists():
        findings.append(f'Missing rollback rehearsal log: {ROLLBACK_REHEARSAL_LOG_RELATIVE_PATH}.')
        return findings

    markdown_text = _read_text(rehearsal_log_path)
    normalized_text = markdown_text.lower()
    for required_heading in REQUIRED_ROLLBACK_REHEARSAL_HEADINGS:
        if required_heading not in markdown_text:
            findings.append(f'Missing rollback rehearsal heading: {required_heading}.')

    if 'date:' not in normalized_text:
        findings.append('Rollback rehearsal log is missing rehearsal date evidence.')
    if 'outcome: pass' not in normalized_text:
        findings.append('Rollback rehearsal log must include at least one pass outcome.')
    if 'deploy-and-rollback.md' not in markdown_text:
        findings.append('Rollback rehearsal log must reference deploy-and-rollback runbook.')
    if 'migration-failback.md' not in markdown_text:
        findings.append('Rollback rehearsal log must reference migration-failback runbook.')
    if _contains_placeholder(markdown_text):
        findings.append('Rollback rehearsal log contains placeholder content.')

    return findings


def _validate_deployment_artifacts(repo_root: Path) -> list[str]:

    '''
    Create deployment artifact and environment-contract validation findings.

    Args:
    repo_root (Path): Repository root path.

    Returns:
    list[str]: Human-readable validation finding messages.
    '''

    findings: list[str] = []
    for relative_path in REQUIRED_DEPLOYMENT_ARTIFACT_PATHS:
        artifact_path = repo_root / relative_path
        if not artifact_path.exists():
            findings.append(f'Missing deployment artifact: {relative_path}.')

    contract_path = repo_root / DEPLOYMENT_ENVIRONMENT_CONTRACT_RELATIVE_PATH
    if not contract_path.exists():
        findings.append(
            'Missing deployment environment contract: '
            f'{DEPLOYMENT_ENVIRONMENT_CONTRACT_RELATIVE_PATH}.',
        )
    else:
        contract_text = _read_text(contract_path)
        if _contains_placeholder(contract_text):
            findings.append('Deployment environment contract contains placeholder content.')

        for heading in REQUIRED_DEPLOYMENT_CONTRACT_HEADINGS:
            if heading not in contract_text:
                findings.append(f'Missing deployment contract heading: {heading}.')

        if 'DATABASE_URL' not in contract_text:
            findings.append('Deployment environment contract is missing DATABASE_URL requirement.')
        if 'GITHUB_TOKEN' not in contract_text:
            findings.append('Deployment environment contract is missing GITHUB_TOKEN requirement.')
        if 'VITE_AGENT1_API_BASE_URL' not in contract_text:
            findings.append(
                'Deployment environment contract is missing VITE_AGENT1_API_BASE_URL requirement.',
            )

    render_blueprint_path = repo_root / 'render.yaml'
    if render_blueprint_path.exists():
        render_blueprint_text = _read_text(render_blueprint_path)
        for snippet in REQUIRED_RENDER_BLUEPRINT_SNIPPETS:
            if snippet not in render_blueprint_text:
                findings.append(f'render.yaml is missing required snippet: {snippet}.')

    return findings


def main() -> int:

    '''
    Compute process exit code for operational-readiness validation gate.

    Returns:
    int: Zero when validation passes, one when validation fails.
    '''

    repo_root = _get_repo_root()
    findings = [
        *_validate_runbook_set(repo_root),
        *_validate_operational_readiness_evidence(repo_root),
        *_validate_service_level_policy(repo_root),
        *_validate_alert_routing_matrix(repo_root),
        *_validate_incident_response_policy(repo_root),
        *_validate_release_control(repo_root),
        *_validate_rollback_rehearsal_log(repo_root),
        *_validate_deployment_artifacts(repo_root),
    ]
    if len(findings) != 0:
        print('Operational readiness validation failed:')
        for finding in findings:
            print(f'- {finding}')
        return 1

    print('Operational readiness validation passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
