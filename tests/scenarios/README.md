# Scenario Tests

Deterministic scenario harness for spec behavior-matrix coverage.

## Files

- `catalog.json`: scenario IDs and bound backend pytest node IDs.
- `pr-smoke-catalog.json`: minimal backend scenario IDs and frontend Playwright specs for PR smoke gate.
- `pr-smoke-env-contract.md`: required and optional environment variables for PR smoke execution.
- `pr_smoke_run.py`: backend PR smoke runner with junit artifact output support.
- `run.py`: executes catalog scenarios against `apps/backend` tests.

## Local Run

- `source venv/bin/activate`
- `python tests/scenarios/run.py`

Optional filter:

- `AGENT1_SCENARIO_IDS=SCN_ISSUE_MENTION_RESPONSE,SCN_SELF_TRIGGER_SUPPRESSION python tests/scenarios/run.py`
