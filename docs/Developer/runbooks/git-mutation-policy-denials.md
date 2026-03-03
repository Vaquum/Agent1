# Git Mutation Policy Denials

## Scope

Incident response for Codex-runtime task blocks caused by git mutation allowlist or denylist policy enforcement.

## Detection Signals

- Codex task result returns `blocked` with `blocked_git_command` metadata.
- Repeated blocked tasks for the same repository scope after policy updates.
- Task execution logs contain command lines matching denylist entries.

## Immediate Containment

1. Preserve blocked task payloads (`task_id`, `blocked_git_command`, `trace_id`).
2. Pause automated retries for the impacted task stream.
3. Confirm policy version currently loaded by runtime.

## Diagnosis

1. Compare `blocked_git_command` against:
   - `controls/policies/default.json` `deny_git_commands`,
   - `controls/policies/default.json` `allowed_git_mutation_commands`.
2. Determine whether the command should be:
   - denied permanently, or
   - added to allowlist with explicit constraints.
3. Confirm command intent is aligned with branch/permission policy before changing controls.

## Remediation

1. If denial is expected:
   - keep policy unchanged,
   - close task with operator note.
2. If command is required and safe:
   - update `allowed_git_mutation_commands`,
   - keep `deny_git_commands` precedence intact,
   - run policy validation and targeted codex-executor tests.
3. Redeploy runtime with updated controls and verify blocked-command metric returns to baseline.

## Exit Criteria

- No repeated blocked tasks for approved command paths.
- Denylist commands remain blocked in tests and runtime.
- Updated policy and runbook links are reflected in developer docs.
