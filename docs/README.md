# Agent1 User Docs

This directory contains user-facing documentation for capabilities, configuration, and operations.

Current operations dashboard capability:

- Dashboard UI renders recent jobs, transitions, and events with filter and pagination controls.
- Dashboard data source is `GET /dashboard/overview` with optional filters for `entity_key`, `job_id`, `trace_id`, and `status`.
- Dashboard supports single-job drill-down via `GET /dashboard/jobs/{job_id}/timeline`.
- Timeline drill-down includes event detail inspection with transition correlation and trace-based pivot filtering.
