from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.control_schemas import RolloutPolicyControl


class RolloutStageGateResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    stage_id: str = Field(min_length=1)
    passed: bool
    required_health_signals: list[str] = Field(default_factory=list)
    missing_health_signals: list[str] = Field(default_factory=list)
    failing_health_signals: list[str] = Field(default_factory=list)


class RolloutStageGateEvaluator:
    def __init__(self, rollout_policy: RolloutPolicyControl) -> None:
        self._required_signals_by_stage = {
            stage.stage_id: list(stage.required_health_signals)
            for stage in rollout_policy.stages
        }

    def list_stages(self) -> list[str]:

        '''
        Create ordered rollout stage identifiers from configured rollout policy.

        Returns:
        list[str]: Ordered rollout stage identifiers.
        '''

        return list(self._required_signals_by_stage.keys())

    def evaluate_stage(self, stage_id: str, signal_health: dict[str, bool]) -> RolloutStageGateResult:

        '''
        Create stage-gate evaluation result from configured stage requirements and health signals.

        Args:
        stage_id (str): Rollout stage identifier to evaluate.
        signal_health (dict[str, bool]): Health status by signal identifier.

        Returns:
        RolloutStageGateResult: Stage-gate evaluation result for requested stage.
        '''

        required_signals = self._required_signals_by_stage.get(stage_id)
        if required_signals is None:
            message = f'Unknown rollout stage: {stage_id}'
            raise ValueError(message)

        missing_health_signals: list[str] = []
        failing_health_signals: list[str] = []
        for signal_id in required_signals:
            if signal_id not in signal_health:
                missing_health_signals.append(signal_id)
                continue

            if signal_health[signal_id] is False:
                failing_health_signals.append(signal_id)

        passed = len(missing_health_signals) == 0 and len(failing_health_signals) == 0
        return RolloutStageGateResult(
            stage_id=stage_id,
            passed=passed,
            required_health_signals=required_signals,
            missing_health_signals=missing_health_signals,
            failing_health_signals=failing_health_signals,
        )


__all__ = ['RolloutStageGateEvaluator', 'RolloutStageGateResult']
