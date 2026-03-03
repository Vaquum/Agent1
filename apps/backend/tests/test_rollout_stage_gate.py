from __future__ import annotations

import pytest

from agent1.core.control_schemas import RolloutPolicyControl
from agent1.core.services.rollout_stage_gate import RolloutStageGateEvaluator


def _create_rollout_policy() -> RolloutPolicyControl:
    return RolloutPolicyControl.model_validate(
        {
            'health_signals': [
                {
                    'signal_id': 'side_effect_success_rate',
                    'description': 'side effect success signal',
                },
                {
                    'signal_id': 'lease_violation_rate',
                    'description': 'lease violation signal',
                },
            ],
            'stages': [
                {
                    'stage_id': 'dev_active',
                    'description': 'dev active stage',
                    'required_health_signals': [
                        'side_effect_success_rate',
                        'lease_violation_rate',
                    ],
                }
            ],
        }
    )


def test_rollout_stage_gate_evaluator_passes_when_required_signals_are_healthy() -> None:
    evaluator = RolloutStageGateEvaluator(rollout_policy=_create_rollout_policy())

    result = evaluator.evaluate_stage(
        stage_id='dev_active',
        signal_health={
            'side_effect_success_rate': True,
            'lease_violation_rate': True,
        },
    )

    assert result.passed is True
    assert result.required_health_signals == ['side_effect_success_rate', 'lease_violation_rate']
    assert result.missing_health_signals == []
    assert result.failing_health_signals == []


def test_rollout_stage_gate_evaluator_reports_missing_and_failing_signals() -> None:
    evaluator = RolloutStageGateEvaluator(rollout_policy=_create_rollout_policy())

    result = evaluator.evaluate_stage(
        stage_id='dev_active',
        signal_health={
            'side_effect_success_rate': False,
        },
    )

    assert result.passed is False
    assert result.missing_health_signals == ['lease_violation_rate']
    assert result.failing_health_signals == ['side_effect_success_rate']


def test_rollout_stage_gate_evaluator_raises_for_unknown_stage() -> None:
    evaluator = RolloutStageGateEvaluator(rollout_policy=_create_rollout_policy())

    with pytest.raises(ValueError, match='Unknown rollout stage'):
        evaluator.evaluate_stage(stage_id='prod_canary', signal_health={})
