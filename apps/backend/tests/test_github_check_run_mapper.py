from __future__ import annotations

from agent1.adapters.github.check_run_mapper import GitHubCheckRunMapper
from agent1.core.ingress_contracts import IngressEventType


def test_check_run_mapper_maps_failed_checks_only() -> None:
    mapper = GitHubCheckRunMapper()
    payloads = [
        {
            'id': 2001,
            'name': 'unit-tests',
            'status': 'completed',
            'conclusion': 'failure',
            'completed_at': '2026-03-03T11:00:00Z',
            'app': {'slug': 'github-actions'},
        },
        {
            'id': 2002,
            'name': 'lint',
            'status': 'completed',
            'conclusion': 'success',
            'completed_at': '2026-03-03T11:01:00Z',
            'app': {'slug': 'github-actions'},
        },
    ]

    mapped_events = mapper.map_check_runs(
        repository='Vaquum/Agent1',
        pull_number=90,
        check_run_payloads=payloads,
        event_seed='evt_seed',
    )

    assert len(mapped_events) == 1
    assert mapped_events[0].event_type == IngressEventType.PR_CI_FAILED
