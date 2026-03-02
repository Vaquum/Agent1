# Scenario Tests

Deterministic scenario harness for spec behavior-matrix coverage.

## Files

- `catalog.json`: scenario IDs and bound backend pytest node IDs.
- `run.py`: executes catalog scenarios against `apps/backend` tests.

## Local Run

- `source venv/bin/activate`
- `python tests/scenarios/run.py`

Optional filter:

- `AGENT1_SCENARIO_IDS=SCN_ISSUE_MENTION_RESPONSE,SCN_SELF_TRIGGER_SUPPRESSION python tests/scenarios/run.py`
