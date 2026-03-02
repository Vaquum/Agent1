# Behavior Matrix

Behavior scenarios and expected outcomes are defined in `spec.md`.

This file will track executable scenario IDs, assertions, and coverage status.

Current coverage includes self-trigger prevention for comment-driven events, bot-origin review-context filtering, deterministic PR author follow-up handling for review feedback and CI failures, Codex-backed remediation attempts for PR author follow-up workflows, runtime mode/scope enforcement with non-active zero-write behavior, startup fail-fast active-scope ownership fencing, deterministic scenario harness execution via `tests/scenarios/catalog.json`, live GitHub sandbox smoke checks against `Vaquum/Agent1`, dashboard overview filtering/pagination on recent jobs/transitions/events, and per-job dashboard timeline drill-down coverage including event detail inspection, reason-based transition correlation, and trace pivot filtering.
