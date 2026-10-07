from __future__ import annotations

from dataclasses import dataclass

from .risk import RiskLevel


@dataclass(frozen=True)
class PolicyDecision:
    """Deterministic policy decision for a remediation."""

    accepted: bool
    requires_human_review: bool
    reason: str


class PolicyGate:
    """
    Deterministic final policy authority.

    AI agents cannot override this gate.
    """

    def evaluate(
        self,
        *,
        risk_level: RiskLevel,
        verification_passed: bool,
        regression_passed: bool,
        auto_heal: bool,
    ) -> PolicyDecision:
        """
        Decide whether a remediation may be accepted.
        """

        if not verification_passed:
            return PolicyDecision(
                accepted=False,
                requires_human_review=False,
                reason=(
                    "Candidate verification failed."
                ),
            )

        if not regression_passed:
            return PolicyDecision(
                accepted=False,
                requires_human_review=False,
                reason=(
                    "Regression gate failed."
                ),
            )

        if not auto_heal:
            return PolicyDecision(
                accepted=False,
                requires_human_review=True,
                reason=(
                    "Automatic healing is disabled."
                ),
            )

        if risk_level == RiskLevel.CRITICAL:
            return PolicyDecision(
                accepted=False,
                requires_human_review=True,
                reason=(
                    "CRITICAL risk requires human review."
                ),
            )

        if risk_level == RiskLevel.HIGH:
            return PolicyDecision(
                accepted=False,
                requires_human_review=True,
                reason=(
                    "HIGH risk changes require human review."
                ),
            )

        return PolicyDecision(
            accepted=True,
            requires_human_review=False,
            reason=(
                "Verification, regression, and policy checks passed."
            ),
        )