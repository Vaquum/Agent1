from __future__ import annotations

from agent1.core.control_schemas import ReleasePromotionPolicyControl
from agent1.core.services.release_promotion_gate_service import ReleasePromotionGateService


def _create_release_promotion_gate_service() -> ReleasePromotionGateService:
    release_promotion_policy = ReleasePromotionPolicyControl.model_validate(
        {
            'preconditions': [
                {
                    'precondition_id': 'operational_readiness_gate_passed',
                    'description': 'Operational readiness gate passed.',
                },
                {
                    'precondition_id': 'stop_the_line_clear',
                    'description': 'No active stop-the-line breach.',
                },
            ]
        }
    )
    return ReleasePromotionGateService(release_promotion_policy=release_promotion_policy)


def test_release_promotion_gate_service_lists_required_preconditions() -> None:
    gate_service = _create_release_promotion_gate_service()

    required_preconditions = gate_service.list_required_preconditions()

    assert required_preconditions == [
        'operational_readiness_gate_passed',
        'stop_the_line_clear',
    ]


def test_release_promotion_gate_service_passes_when_all_preconditions_are_true() -> None:
    gate_service = _create_release_promotion_gate_service()

    decision = gate_service.evaluate(
        evidence={
            'operational_readiness_gate_passed': True,
            'stop_the_line_clear': True,
        }
    )

    assert decision.passed is True
    assert decision.failed_preconditions == []
    assert decision.evidence == {
        'operational_readiness_gate_passed': True,
        'stop_the_line_clear': True,
    }


def test_release_promotion_gate_service_fails_when_any_precondition_is_false_or_missing() -> None:
    gate_service = _create_release_promotion_gate_service()

    decision = gate_service.evaluate(
        evidence={
            'operational_readiness_gate_passed': True,
        }
    )

    assert decision.passed is False
    assert decision.failed_preconditions == ['stop_the_line_clear']
    assert decision.evidence == {
        'operational_readiness_gate_passed': True,
        'stop_the_line_clear': False,
    }
