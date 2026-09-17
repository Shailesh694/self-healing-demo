from __future__ import annotations

from dataclasses import dataclass

from .analysis.policy import PolicyDecision, evaluate_policy
from .analysis.scorer import RiskAssessment


@dataclass(frozen=True)
class RepairPolicy:
    require_tests: bool = True
    allow_auto_apply: bool = False
    allow_rollback: bool = True


def evaluate_repair_policy(
    *,
    risk: RiskAssessment,
) -> PolicyDecision:
    """
    Decide whether a repair is allowed based on its risk tier.

    Risk decisions are deterministic:
    LOW      -> allowed
    MEDIUM   -> allowed with verification
    HIGH     -> human approval required
    CRITICAL -> human approval required
    """

    return evaluate_policy(risk)


def can_auto_apply(
    *,
    risk: RiskAssessment,
    policy: RepairPolicy,
) -> bool:
    """
    Decide whether a repair may modify the repository automatically.

    The global allow_auto_apply switch is a hard safety gate.
    Risk policy is evaluated separately.
    """

    if not policy.allow_auto_apply:
        return False

    decision = evaluate_repair_policy(risk=risk)

    return decision.allowed