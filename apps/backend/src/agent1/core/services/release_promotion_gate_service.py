from __future__ import annotations

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from agent1.core.control_schemas import ReleasePromotionPolicyControl


class ReleasePromotionDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')

    passed: bool
    required_preconditions: list[str] = Field(default_factory=list)
    failed_preconditions: list[str] = Field(default_factory=list)
    evidence: dict[str, bool] = Field(default_factory=dict)


class ReleasePromotionGateService:
    def __init__(self, release_promotion_policy: ReleasePromotionPolicyControl) -> None:
        self._required_preconditions = [
            precondition.precondition_id for precondition in release_promotion_policy.preconditions
        ]

    def list_required_preconditions(self) -> list[str]:

        '''
        Create ordered release-promotion precondition identifiers from policy controls.

        Returns:
        list[str]: Ordered required precondition identifiers.
        '''

        return list(self._required_preconditions)

    def evaluate(self, evidence: dict[str, bool]) -> ReleasePromotionDecision:

        '''
        Create release-promotion gate decision from required preconditions and evidence.

        Args:
        evidence (dict[str, bool]): Boolean evidence values keyed by precondition identifier.

        Returns:
        ReleasePromotionDecision: Release-promotion gate decision payload.
        '''

        failed_preconditions: list[str] = []
        for precondition_id in self._required_preconditions:
            if evidence.get(precondition_id) is not True:
                failed_preconditions.append(precondition_id)

        return ReleasePromotionDecision(
            passed=len(failed_preconditions) == 0,
            required_preconditions=self.list_required_preconditions(),
            failed_preconditions=failed_preconditions,
            evidence={precondition_id: evidence.get(precondition_id) is True for precondition_id in self._required_preconditions},
        )


__all__ = ['ReleasePromotionDecision', 'ReleasePromotionGateService']
