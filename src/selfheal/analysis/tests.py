from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class TestResult:
    passed: bool
    output: str
    return_code: int


def run_tests(
    *,
    project_path: str = ".",
    test_command: list[str] | None = None,
) -> TestResult:
    """
    Run the project's test suite and capture the result.
    """

    command = test_command or [
        "python",
        "-m",
        "pytest",
        ".",
        "-q",
    ]

    process = subprocess.run(
        command,
        cwd=project_path,
        capture_output=True,
        text=True,
    )

    output = (
        process.stdout
        + "\n"
        + process.stderr
    ).strip()

    return TestResult(
        passed=process.returncode == 0,
        output=output,
        return_code=process.returncode,
    )