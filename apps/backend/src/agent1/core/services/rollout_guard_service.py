from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.contracts import RuntimeMode
from agent1.core.services.rollout_stage_gate import RolloutStageGateEvaluator

STAGE_GATE_FAILED_MODE_DOWNGRADE = 'stage_gate_failed_mode_downgrade'
STAGE_GATE_FAILED_NO_MODE_CHANGE = 'stage_gate_failed_no_mode_change'
STAGE_GATE_PASSED = 'stage_gate_passed'


class RolloutGuardDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')

    stage_id: str = Field(min_length=1)
    stage_passed: bool
    rollback_triggered: bool
    current_mode: RuntimeMode
    target_mode: RuntimeMode
    reason: str = Field(min_length=1)
    missing_health_signals: list[str] = Field(default_factory=list)
    failing_health_signals: list[str] = Field(default_factory=list)


class RolloutGuardService:
    def __init__(self, stage_gate_evaluator: RolloutStageGateEvaluator) -> None:
        self._stage_gate_evaluator = stage_gate_evaluator

    def evaluate_stage_for_rollback(
        self,
        stage_id: str,
        signal_health: dict[str, bool],
        current_mode: RuntimeMode,
    ) -> RolloutGuardDecision:

        '''
        Create rollback decision from rollout stage-gate outcome and current runtime mode.

        Args:
        stage_id (str): Rollout stage identifier.
        signal_health (dict[str, bool]): Health status by signal identifier.
        current_mode (RuntimeMode): Active runtime mode at decision time.

        Returns:
        RolloutGuardDecision: Deterministic rollback decision for evaluated stage.
        '''

        stage_result = self._stage_gate_evaluator.evaluate_stage(
            stage_id=stage_id,
            signal_health=signal_health,
        )
        if stage_result.passed:
            return RolloutGuardDecision(
                stage_id=stage_id,
                stage_passed=True,
                rollback_triggered=False,
                current_mode=current_mode,
                target_mode=current_mode,
                reason=STAGE_GATE_PASSED,
                missing_health_signals=stage_result.missing_health_signals,
                failing_health_signals=stage_result.failing_health_signals,
            )

        if current_mode == RuntimeMode.ACTIVE:
            return RolloutGuardDecision(
                stage_id=stage_id,
                stage_passed=False,
                rollback_triggered=True,
                current_mode=current_mode,
                target_mode=RuntimeMode.SHADOW,
                reason=STAGE_GATE_FAILED_MODE_DOWNGRADE,
                missing_health_signals=stage_result.missing_health_signals,
                failing_health_signals=stage_result.failing_health_signals,
            )

        return RolloutGuardDecision(
            stage_id=stage_id,
            stage_passed=False,
            rollback_triggered=False,
            current_mode=current_mode,
            target_mode=current_mode,
            reason=STAGE_GATE_FAILED_NO_MODE_CHANGE,
            missing_health_signals=stage_result.missing_health_signals,
            failing_health_signals=stage_result.failing_health_signals,
        )


__all__ = [
    'RolloutGuardDecision',
    'RolloutGuardService',
    'STAGE_GATE_FAILED_MODE_DOWNGRADE',
    'STAGE_GATE_FAILED_NO_MODE_CHANGE',
    'STAGE_GATE_PASSED',
]
