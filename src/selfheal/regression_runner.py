from __future__ import annotations

from .analysis.tests import run_tests
from .regression import CheckResult
from .regression_gate import (
    RegressionGate,
    RegressionGateResult,
)
from .regression_scope import FileSnapshot
from .regression_snapshot import snapshot_files


def evaluate_regression(
    *,
    baseline_checks: list[CheckResult],
    candidate_checks: list[CheckResult],
    baseline_files: list[FileSnapshot],
    candidate_files: list[FileSnapshot],
    approved_files: set[str],
) -> RegressionGateResult:
    """
    Run the complete deterministic regression gate.
    """

    gate = RegressionGate()

    return gate.evaluate(
        baseline_checks=baseline_checks,
        candidate_checks=candidate_checks,
        baseline_files=baseline_files,
        candidate_files=candidate_files,
        approved_files=approved_files,
    )


def capture_verification(
    *,
    repository_path: str,
    test_command: list[str] | None = None,
) -> CheckResult:
    """
    Run the repository test suite and convert the result
    into the deterministic regression-check format.
    """

    result = run_tests(
        project_path=repository_path,
        test_command=test_command,
    )

    return CheckResult(
        name="pytest",
        passed=result.passed,
        return_code=result.return_code,
        stdout=result.output,
        stderr="",
    )


def capture_regression_baseline(
    *,
    repository_path: str,
    test_command: list[str] | None = None,
) -> tuple[CheckResult, list[FileSnapshot]]:
    """
    Capture the repository state before remediation.

    No files are modified.
    """

    check = capture_verification(
        repository_path=repository_path,
        test_command=test_command,
    )

    files = snapshot_files(repository_path)

    return check, files


def capture_regression_candidate(
    *,
    repository_path: str,
    test_command: list[str] | None = None,
) -> tuple[CheckResult, list[FileSnapshot]]:
    """
    Capture the repository state after remediation.

    No files are modified by this function.
    """

    check = capture_verification(
        repository_path=repository_path,
        test_command=test_command,
    )

    files = snapshot_files(repository_path)

    return check, files