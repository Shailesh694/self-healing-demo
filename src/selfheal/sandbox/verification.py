from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .executor import SandboxExecutor, SandboxResult


@dataclass(frozen=True)
class VerificationResult:
    """Verification result for a candidate repair."""

    passed: bool
    sandbox_result: SandboxResult
    command: tuple[str, ...]


class SandboxVerifier:
    """
    Run verification commands against an isolated repository copy.

    The real repository is never modified.
    """

    def __init__(self, timeout_seconds: int = 60):
        self.executor = SandboxExecutor(
            timeout_seconds=timeout_seconds
        )

    def verify(
        self,
        *,
        repository_path: str | Path,
        command: list[str],
    ) -> VerificationResult:
        if not command:
            raise ValueError(
                "Verification command cannot be empty"
            )

        result = self.executor.run(
            source_path=repository_path,
            command=command,
        )

        return VerificationResult(
            passed=result.passed,
            sandbox_result=result,
            command=tuple(command),
        )