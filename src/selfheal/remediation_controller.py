from __future__ import annotations

from dataclasses import dataclass

from .policy_gate import PolicyDecision, PolicyGate
from .retry import RetryAttempt, RetryController
from .risk import RiskLevel


@dataclass(frozen=True)
class RemediationAttemptResult:
    """Result of one candidate remediation attempt."""

    attempt: int
    verification_passed: bool
    regression_passed: bool
    policy: PolicyDecision
    error: str | None = None


@dataclass(frozen=True)
class RemediationControllerResult:
    """Final bounded remediation decision."""

    accepted: bool
    requires_human_review: bool
    exhausted: bool
    attempts: tuple[RemediationAttemptResult, ...]


class RemediationController:
    """
    Deterministic controller for bounded remediation attempts.

    The controller does not generate patches itself.
    It decides what to do with verification, regression,
    risk, and policy results.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 3,
    ):
        self.retry_controller = RetryController(
            max_attempts=max_attempts
        )
        self.policy_gate = PolicyGate()

    def evaluate(
        self,
        *,
        attempts: list[RemediationAttemptResult],
        risk_level: RiskLevel,
        auto_heal: bool,
    ) -> RemediationControllerResult:
        retry_attempts = [
            RetryAttempt(
                attempt=attempt.attempt,
                passed=(
                    attempt.verification_passed
                    and attempt.regression_passed
                    and attempt.policy.accepted
                ),
                error=attempt.error,
            )
            for attempt in attempts
        ]

        retry_result = self.retry_controller.record(
            retry_attempts
        )

        accepted_attempt = next(
        (
            attempt
            for attempt in attempts
            if (
                attempt.policy.accepted
                and attempt.verification_passed
                and attempt.regression_passed
                )
            ),
            None,
        )

        if accepted_attempt is not None:
            return RemediationControllerResult(
                accepted=True,
                requires_human_review=False,
                exhausted=False,
                attempts=tuple(attempts),
            )

        human_review_required = any(
            attempt.policy.requires_human_review
            for attempt in attempts
        )

        return RemediationControllerResult(
            accepted=False,
            requires_human_review=human_review_required,
            exhausted=retry_result.exhausted,
            attempts=tuple(attempts),
        )

    def create_attempt(
        self,
        *,
        attempt: int,
        verification_passed: bool,
        regression_passed: bool,
        risk_level: RiskLevel,
        auto_heal: bool,
        error: str | None = None,
    ) -> RemediationAttemptResult:
        policy = self.policy_gate.evaluate(
            risk_level=risk_level,
            verification_passed=verification_passed,
            regression_passed=regression_passed,
            auto_heal=auto_heal,
        )

        return RemediationAttemptResult(
            attempt=attempt,
            verification_passed=verification_passed,
            regression_passed=regression_passed,
            policy=policy,
            error=error,
        )