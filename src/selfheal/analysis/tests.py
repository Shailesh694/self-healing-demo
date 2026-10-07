from __future__ import annotations

import os
import subprocess
import sys
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
        sys.executable,
        "-m",
        "pytest",
        ".",
        "-q",
    ]

    try:
        process = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("SELFHEAL_TEST_TIMEOUT", "300")),
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            output="test run timed out",
            return_code=-1,
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