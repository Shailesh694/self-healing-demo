from __future__ import annotations

from dataclasses import dataclass

from .regression import (
    CheckResult,
    RegressionResult,
    compare_results,
)
from .regression_scope import (
    FileSnapshot,
    ScopeRegressionResult,
    compare_file_scope,
)


@dataclass(frozen=True)
class RegressionGateResult:
    """Combined deterministic regression decision."""

    passed: bool
    verification: RegressionResult
    scope: ScopeRegressionResult
    reasons: tuple[str, ...]


class RegressionGate:
    """
    Hard deterministic regression gate.

    AI output has no authority over this decision.
    """

    def evaluate(
        self,
        *,
        baseline_checks: list[CheckResult],
        candidate_checks: list[CheckResult],
        baseline_files: list[FileSnapshot],
        candidate_files: list[FileSnapshot],
        approved_files: set[str],
    ) -> RegressionGateResult:
        verification = compare_results(
            baseline_checks,
            candidate_checks,
        )

        scope = compare_file_scope(
            baseline_files,
            candidate_files,
            approved_files,
        )

        reasons: list[str] = []

        if not verification.passed:
            reasons.extend(
                verification.regressions
            )

        if not scope.passed:
            reasons.extend(
                f"Unexpected file change: {path}"
                for path in scope.unexpected_files
            )

        return RegressionGateResult(
            passed=(
                verification.passed
                and scope.passed
            ),
            verification=verification,
            scope=scope,
            reasons=tuple(reasons),
        )