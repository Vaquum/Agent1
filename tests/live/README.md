# Live Tests

Real GitHub smoke tests executed against the `Vaquum/Agent1` sandbox scope.

## Environment

- `AGENT1_LIVE_GITHUB_TOKEN`: GitHub token with read access to the sandbox repo.
- `AGENT1_LIVE_REPOSITORY`: target repository (default: `Vaquum/Agent1`).
- `AGENT1_LIVE_REQUIRED`: `true` to fail when token is missing instead of skip.

## Local Run

- `source venv/bin/activate`
- `python tests/live/run.py`
