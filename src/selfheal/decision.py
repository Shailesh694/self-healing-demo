from __future__ import annotations

from dataclasses import dataclass

from .analysis.policy import evaluate_policy
from .analysis.scorer import RiskAssessment
from .policy import RepairPolicy, can_auto_apply


@dataclass
class RepairDecision:
    action: str
    reason: str


def decide_repair(
    *,
    risk: RiskAssessment,
    policy: RepairPolicy,
    tests_available: bool = True,
) -> RepairDecision:
    """
    Decide what should happen with a proposed repair.

    Risk tier determines whether the change is eligible.
    Tests determine whether verification can proceed.
    The global auto-apply switch remains a separate safety gate.
    """

    policy_decision = evaluate_policy(risk)

    if not policy_decision.allowed:
        return RepairDecision(
            action="review",
            reason=policy_decision.reason,
        )

    if policy.require_tests and not tests_available:
        return RepairDecision(
            action="review",
            reason="Tests are required before automatic repair",
        )

    if can_auto_apply(
        risk=risk,
        policy=policy,
    ):
        return RepairDecision(
            action="auto_apply",
            reason="Policy allows automatic repair",
        )

    return RepairDecision(
        action="review",
        reason="Repair requires human review",
    )