from __future__ import annotations

from dataclasses import dataclass

from .analysis.tests import run_tests


@dataclass
class VerificationResult:
    passed: bool
    output: str
    return_code: int


def verify(
    *,
    project_path: str = ".",
) -> VerificationResult:
    """
    Verify the repository by running its test suite.
    """

    result = run_tests(
        project_path=project_path,
    )

    return VerificationResult(
        passed=result.passed,
        output=result.output,
        return_code=result.return_code,
    )