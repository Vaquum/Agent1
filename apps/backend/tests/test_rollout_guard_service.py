from __future__ import annotations

from agent1.core.contracts import RuntimeMode
from agent1.core.control_schemas import RolloutPolicyControl
from agent1.core.services.rollout_guard_service import RolloutGuardService
from agent1.core.services.rollout_guard_service import STAGE_GATE_FAILED_MODE_DOWNGRADE
from agent1.core.services.rollout_guard_service import STAGE_GATE_FAILED_NO_MODE_CHANGE
from agent1.core.services.rollout_guard_service import STAGE_GATE_PASSED
from agent1.core.services.rollout_stage_gate import RolloutStageGateEvaluator


def _create_guard_service() -> RolloutGuardService:
    rollout_policy = RolloutPolicyControl.model_validate(
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
                    'stage_id': 'prod_canary',
                    'description': 'prod canary stage',
                    'required_health_signals': [
                        'side_effect_success_rate',
                        'lease_violation_rate',
                    ],
                }
            ],
        }
    )
    stage_gate_evaluator = RolloutStageGateEvaluator(rollout_policy=rollout_policy)
    return RolloutGuardService(stage_gate_evaluator=stage_gate_evaluator)


def test_rollout_guard_service_triggers_mode_downgrade_on_stage_failure_in_active_mode() -> None:
    guard_service = _create_guard_service()

    decision = guard_service.evaluate_stage_for_rollback(
        stage_id='prod_canary',
        signal_health={
            'side_effect_success_rate': False,
            'lease_violation_rate': True,
        },
        current_mode=RuntimeMode.ACTIVE,
    )

    assert decision.stage_passed is False
    assert decision.rollback_triggered is True
    assert decision.current_mode == RuntimeMode.ACTIVE
    assert decision.target_mode == RuntimeMode.SHADOW
    assert decision.reason == STAGE_GATE_FAILED_MODE_DOWNGRADE
    assert decision.failing_health_signals == ['side_effect_success_rate']


def test_rollout_guard_service_keeps_current_mode_when_stage_passes() -> None:
    guard_service = _create_guard_service()

    decision = guard_service.evaluate_stage_for_rollback(
        stage_id='prod_canary',
        signal_health={
            'side_effect_success_rate': True,
            'lease_violation_rate': True,
        },
        current_mode=RuntimeMode.ACTIVE,
    )

    assert decision.stage_passed is True
    assert decision.rollback_triggered is False
    assert decision.current_mode == RuntimeMode.ACTIVE
    assert decision.target_mode == RuntimeMode.ACTIVE
    assert decision.reason == STAGE_GATE_PASSED


def test_rollout_guard_service_keeps_non_active_mode_on_stage_failure() -> None:
    guard_service = _create_guard_service()

    decision = guard_service.evaluate_stage_for_rollback(
        stage_id='prod_canary',
        signal_health={'side_effect_success_rate': False},
        current_mode=RuntimeMode.SHADOW,
    )

    assert decision.stage_passed is False
    assert decision.rollback_triggered is False
    assert decision.current_mode == RuntimeMode.SHADOW
    assert decision.target_mode == RuntimeMode.SHADOW
    assert decision.reason == STAGE_GATE_FAILED_NO_MODE_CHANGE
    assert decision.missing_health_signals == ['lease_violation_rate']
    assert decision.failing_health_signals == ['side_effect_success_rate']
