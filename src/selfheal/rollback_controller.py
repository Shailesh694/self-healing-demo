from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RollbackReason(str, Enum):
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    REGRESSION_FAILURE = "REGRESSION_FAILURE"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    POLICY_REJECTION = "POLICY_REJECTION"


@dataclass(frozen=True)
class RollbackDecision:
    """Deterministic decision about whether rollback is required."""

    required: bool
    reason: RollbackReason | None = None


class RollbackController:
    """
    Decide when a candidate remediation must be rolled back.

    This controller does not perform Git operations itself.
    Git execution remains the responsibility of the Git abstraction.
    """

    def evaluate(
        self,
        *,
        verification_passed: bool,
        regression_passed: bool,
        retry_exhausted: bool,
        policy_accepted: bool,
    ) -> RollbackDecision:
        if not verification_passed:
            return RollbackDecision(
                required=True,
                reason=RollbackReason.VERIFICATION_FAILURE,
            )

        if not regression_passed:
            return RollbackDecision(
                required=True,
                reason=RollbackReason.REGRESSION_FAILURE,
            )

        if retry_exhausted:
            return RollbackDecision(
                required=True,
                reason=RollbackReason.RETRY_EXHAUSTED,
            )

        if not policy_accepted:
            return RollbackDecision(
                required=True,
                reason=RollbackReason.POLICY_REJECTION,
            )

        return RollbackDecision(
            required=False,
        )