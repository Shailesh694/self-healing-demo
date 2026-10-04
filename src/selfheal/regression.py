from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    """Result of one verification check."""

    name: str
    passed: bool
    return_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RegressionResult:
    """
    Comparison between baseline and candidate verification.

    A candidate passes only when the required checks pass and
    no previously passing check becomes failing.
    """

    passed: bool
    baseline: tuple[CheckResult, ...]
    candidate: tuple[CheckResult, ...]
    regressions: tuple[str, ...]


def compare_results(
    baseline: list[CheckResult],
    candidate: list[CheckResult],
) -> RegressionResult:
    """
    Compare baseline and candidate verification results.

    Any check that passed in the baseline but fails in the
    candidate is considered a regression.
    """

    baseline_by_name = {
        result.name: result
        for result in baseline
    }

    candidate_by_name = {
        result.name: result
        for result in candidate
    }

    regressions: list[str] = []

    for name, baseline_result in baseline_by_name.items():
        candidate_result = candidate_by_name.get(name)

        if candidate_result is None:
            regressions.append(
                f"Missing candidate check: {name}"
            )
            continue

        if baseline_result.passed and not candidate_result.passed:
            regressions.append(
                f"Regression detected: {name}"
            )

    return RegressionResult(
        passed=not regressions,
        baseline=tuple(baseline),
        candidate=tuple(candidate),
        regressions=tuple(regressions),
    )