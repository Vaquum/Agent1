# Github Rate Limit And Token Failures

## Scope

Incident response for GitHub API credential failures and rate-limit exhaustion.

## Detection Signals

- `401` or `403` authentication/authorization failures from GitHub API.
- `429` responses or explicit rate-limit exhaustion headers.
- Spike in failed `api_call` events in the event journal.

## Immediate Containment

1. Switch runtime mode to `shadow` for affected mutating workflows.
2. Increase polling interval temporarily to reduce API pressure.
3. Preserve request/response metadata required for investigation.

## Diagnosis

1. Validate token presence and correctness in runtime environment.
2. Confirm token owner is expected for the environment identity.
3. Inspect response headers for remaining quota and reset time.
4. Identify high-volume endpoints and repeated retries.

## Remediation

1. Rotate token when credentials are invalid or compromised.
2. Reduce ingress pressure:
   - increase poll interval,
   - disable unnecessary enrichment calls temporarily if needed.
3. Resume normal poll interval after stable quota behavior.
4. Keep strict separation between read/watch credentials and mutating credentials.

## Exit Criteria

- No auth failures in two consecutive poll windows.
- Rate-limit headroom is stable.
- Mutating workflows resume in `active` without repeated API failures.
