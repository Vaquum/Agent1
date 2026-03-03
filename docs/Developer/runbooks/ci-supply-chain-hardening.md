# CI Supply Chain Hardening

Run this procedure when CI supply-chain hardening validation fails.

## Scope

- Workflow action pinning and job-permission drift:
  - `tests/operations/workflow_supply_chain_validation.py`
  - `docs/Developer/ci-token-permissions-policy.json`
- Dependency vulnerability gates:
  - `tests/operations/dependency_vulnerability_gate.py`
  - `docs/Developer/dependency-vulnerability-policy.json`
  - `docs/Developer/dependency-vulnerability-policy.md`

## Validation Commands

1. Validate workflow action pinning and job permissions:
   - `python tests/operations/workflow_supply_chain_validation.py`
2. Validate python vulnerability gate:
   - `python tests/operations/dependency_vulnerability_gate.py --ecosystem python`
3. Validate node vulnerability gate:
   - `python tests/operations/dependency_vulnerability_gate.py --ecosystem node`

## Remediation Steps

1. Replace every third-party workflow action reference with immutable SHA pinning.
2. Update per-job workflow `permissions` blocks to match `ci-token-permissions-policy.json`.
3. For vulnerability findings:
   - prioritize dependency upgrade and lockfile refresh,
   - only add temporary exception entries when remediation is blocked.
4. For each temporary exception:
   - provide explicit risk reason,
   - set near-term expiry date,
   - track remediation ticket.
