# 09 - Sandbox To Production

Navigation: Previous `08-safety-model.md` | Index `README.md` | Next `10-incident-rhythm.md`

Promotion is a confidence process, not a hope process.

## Sandbox First

Start with sandbox labels and branch namespaces.

Prove behavior with realistic events while production remains protected from duplicate handling.

## Promotion Checklist

- Scenario coverage is green.
- Operational readiness gate is green.
- Alert routing and runbooks are current.
- Stop-the-line signals are clear.
- Release promotion preconditions pass.

## Retention Governance In Promotion

- Retention policy drift checks must pass.
- Purge behavior is verified in dry-run before execute.
- Production execute requires explicit acknowledgement.

## Principle

You do not "flip to prod." You graduate to prod.

Related:

- `10-incident-rhythm.md`
- `07-dashboard-signals.md`
- `06-pr-journey.md`

Next: `10-incident-rhythm.md`
