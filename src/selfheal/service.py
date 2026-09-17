from __future__ import annotations

from .analysis.scorer import RiskAssessment
from .decision import decide_repair
from .policy import RepairPolicy
from .state import HealingState
from .status import RepairStatus


class SelfHealService:
    def __init__(
        self,
        policy: RepairPolicy | None = None,
    ) -> None:
        self.policy = policy or RepairPolicy()

    def analyze(
        self,
        *,
        incident_id: str,
        risk: RiskAssessment,
        tests_available: bool = True,
    ) -> dict:
        state = HealingState(
            incident_id=incident_id,
        )

        state.transition(
            RepairStatus.ANALYZING
        )

        decision = decide_repair(
            risk=risk,
            policy=self.policy,
            tests_available=tests_available,
        )

        if decision.action == "reject":
            state.transition(
                RepairStatus.FAILED
            )

        elif decision.action == "review":
            state.transition(
                RepairStatus.PROPOSED
            )

        else:
            state.transition(
                RepairStatus.VALIDATING
            )

        return {
            "incident_id": incident_id,
            "risk": risk,
            "decision": decision,
            "state": state,
        }