from __future__ import annotations

from agent1.core.contracts import RuntimeMode
from agent1.core.control_schemas import StopTheLinePolicyControl
from agent1.core.services.stop_the_line_service import STOP_THE_LINE_CLEAR
from agent1.core.services.stop_the_line_service import STOP_THE_LINE_TRIGGERED_MODE_DOWNGRADE
from agent1.core.services.stop_the_line_service import STOP_THE_LINE_TRIGGERED_NO_MODE_CHANGE
from agent1.core.services.stop_the_line_service import StopTheLineService


def _create_stop_the_line_service() -> StopTheLineService:
    stop_the_line_policy = StopTheLinePolicyControl.model_validate(
        {
            'rules': [
                {
                    'signal_id': 'error_rate',
                    'comparator': 'gte',
                    'threshold': 0.05,
                    'evaluation_window_minutes': 15,
                },
                {
                    'signal_id': 'lease_violation_rate',
                    'comparator': 'gte',
                    'threshold': 0.01,
                    'evaluation_window_minutes': 15,
                },
            ]
        }
    )
    return StopTheLineService(stop_the_line_policy=stop_the_line_policy)


def test_stop_the_line_service_downgrades_active_mode_when_threshold_is_breached() -> None:
    service = _create_stop_the_line_service()

    decision = service.evaluate(
        signal_values={
            'error_rate': 0.06,
            'lease_violation_rate': 0.001,
        },
        current_mode=RuntimeMode.ACTIVE,
    )

    assert decision.triggered is True
    assert decision.rollback_triggered is True
    assert decision.current_mode == RuntimeMode.ACTIVE
    assert decision.target_mode == RuntimeMode.SHADOW
    assert decision.reason == STOP_THE_LINE_TRIGGERED_MODE_DOWNGRADE
    assert len(decision.breached_rules) == 1
    assert decision.breached_rules[0].signal_id == 'error_rate'


def test_stop_the_line_service_exposes_max_rule_evaluation_window_seconds() -> None:
    service = _create_stop_the_line_service()

    window_seconds = service.get_evaluation_window_seconds()

    assert window_seconds == 900


def test_stop_the_line_service_keeps_mode_when_no_thresholds_are_breached() -> None:
    service = _create_stop_the_line_service()

    decision = service.evaluate(
        signal_values={
            'error_rate': 0.01,
            'lease_violation_rate': 0.001,
        },
        current_mode=RuntimeMode.ACTIVE,
    )

    assert decision.triggered is False
    assert decision.rollback_triggered is False
    assert decision.current_mode == RuntimeMode.ACTIVE
    assert decision.target_mode == RuntimeMode.ACTIVE
    assert decision.reason == STOP_THE_LINE_CLEAR
    assert decision.breached_rules == []


def test_stop_the_line_service_keeps_non_active_mode_when_threshold_is_breached() -> None:
    service = _create_stop_the_line_service()

    decision = service.evaluate(
        signal_values={
            'error_rate': 0.06,
            'lease_violation_rate': 0.001,
        },
        current_mode=RuntimeMode.SHADOW,
    )

    assert decision.triggered is True
    assert decision.rollback_triggered is False
    assert decision.current_mode == RuntimeMode.SHADOW
    assert decision.target_mode == RuntimeMode.SHADOW
    assert decision.reason == STOP_THE_LINE_TRIGGERED_NO_MODE_CHANGE
    assert len(decision.breached_rules) == 1
    assert decision.breached_rules[0].signal_id == 'error_rate'
