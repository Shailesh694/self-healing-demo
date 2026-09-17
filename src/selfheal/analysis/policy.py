from __future__ import annotations

from dataclasses import dataclass

from .scorer import RiskAssessment


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def evaluate_policy(risk: RiskAssessment) -> PolicyDecision:
    if risk.tier == "LOW":
        return PolicyDecision(
            allowed=True,
            reason="Low-risk change may proceed.",
        )

    if risk.tier == "MEDIUM":
        return PolicyDecision(
            allowed=True,
            reason="Medium-risk change requires verification.",
        )

    if risk.tier == "HIGH":
        return PolicyDecision(
            allowed=False,
            reason="High-risk changes require human approval.",
        )

    return PolicyDecision(
        allowed=False,
        reason="Critical-risk changes require human approval.",
    )