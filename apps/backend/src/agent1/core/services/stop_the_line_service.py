from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.contracts import RuntimeMode
from agent1.core.control_schemas import StopTheLinePolicyControl
from agent1.core.control_schemas import StopTheLineThresholdRuleControl

STOP_THE_LINE_CLEAR = 'stop_the_line_clear'
STOP_THE_LINE_TRIGGERED_MODE_DOWNGRADE = 'stop_the_line_triggered_mode_downgrade'
STOP_THE_LINE_TRIGGERED_NO_MODE_CHANGE = 'stop_the_line_triggered_no_mode_change'


class StopTheLineBreach(BaseModel):
    model_config = ConfigDict(extra='forbid')

    signal_id: str = Field(min_length=1)
    comparator: str = Field(min_length=1)
    threshold: float
    observed_value: float


class StopTheLineDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')

    triggered: bool
    rollback_triggered: bool
    current_mode: RuntimeMode
    target_mode: RuntimeMode
    reason: str = Field(min_length=1)
    breached_rules: list[StopTheLineBreach] = Field(default_factory=list)


class StopTheLineService:
    def __init__(self, stop_the_line_policy: StopTheLinePolicyControl) -> None:
        self._rules = list(stop_the_line_policy.rules)

    def get_evaluation_window_seconds(self) -> int:

        '''
        Create stop-the-line evaluation window size in seconds from configured rules.

        Returns:
        int: Maximum rule evaluation window in seconds.
        '''

        return max(rule.evaluation_window_minutes for rule in self._rules) * 60

    def evaluate(
        self,
        signal_values: dict[str, float],
        current_mode: RuntimeMode,
    ) -> StopTheLineDecision:

        '''
        Create stop-the-line decision from threshold rules, observed signals, and runtime mode.

        Args:
        signal_values (dict[str, float]): Observed signal values by signal identifier.
        current_mode (RuntimeMode): Active runtime mode at decision time.

        Returns:
        StopTheLineDecision: Threshold evaluation decision with deterministic mode outcome.
        '''

        breached_rules = self._list_breaches(signal_values=signal_values)
        if len(breached_rules) == 0:
            return StopTheLineDecision(
                triggered=False,
                rollback_triggered=False,
                current_mode=current_mode,
                target_mode=current_mode,
                reason=STOP_THE_LINE_CLEAR,
                breached_rules=[],
            )

        if current_mode == RuntimeMode.ACTIVE:
            return StopTheLineDecision(
                triggered=True,
                rollback_triggered=True,
                current_mode=current_mode,
                target_mode=RuntimeMode.SHADOW,
                reason=STOP_THE_LINE_TRIGGERED_MODE_DOWNGRADE,
                breached_rules=breached_rules,
            )

        return StopTheLineDecision(
            triggered=True,
            rollback_triggered=False,
            current_mode=current_mode,
            target_mode=current_mode,
            reason=STOP_THE_LINE_TRIGGERED_NO_MODE_CHANGE,
            breached_rules=breached_rules,
        )

    def _list_breaches(self, signal_values: dict[str, float]) -> list[StopTheLineBreach]:
        breaches: list[StopTheLineBreach] = []
        for rule in self._rules:
            if rule.signal_id not in signal_values:
                continue

            observed_value = signal_values[rule.signal_id]
            if self._is_rule_breached(rule=rule, observed_value=observed_value):
                breaches.append(
                    StopTheLineBreach(
                        signal_id=rule.signal_id,
                        comparator=rule.comparator,
                        threshold=rule.threshold,
                        observed_value=observed_value,
                    )
                )

        return breaches

    def _is_rule_breached(
        self,
        rule: StopTheLineThresholdRuleControl,
        observed_value: float,
    ) -> bool:
        if rule.comparator == 'gt':
            return observed_value > rule.threshold
        if rule.comparator == 'gte':
            return observed_value >= rule.threshold
        if rule.comparator == 'lt':
            return observed_value < rule.threshold

        return observed_value <= rule.threshold


__all__ = [
    'STOP_THE_LINE_CLEAR',
    'STOP_THE_LINE_TRIGGERED_MODE_DOWNGRADE',
    'STOP_THE_LINE_TRIGGERED_NO_MODE_CHANGE',
    'StopTheLineBreach',
    'StopTheLineDecision',
    'StopTheLineService',
]
