from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxResult:
    """Result of a command executed inside a temporary sandbox."""

    passed: bool
    return_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxExecutor:
    """
    Execute verification commands inside an isolated temporary copy.

    The original repository is never modified by this executor.
    """

    def __init__(self, timeout_seconds: int = 60):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.timeout_seconds = timeout_seconds

    def run(
        self,
        *,
        source_path: str | Path,
        command: list[str],
    ) -> SandboxResult:
        """
        Copy the supplied project into a temporary directory and
        execute the command there.

        Environment variables are deliberately restricted.
        """

        source = Path(source_path).resolve()

        if not source.exists():
            raise FileNotFoundError(
                f"Sandbox source does not exist: {source}"
            )

        if not command:
            raise ValueError("Sandbox command cannot be empty")

        import tempfile
        import shutil

        sandbox_dir = Path(
            tempfile.mkdtemp(prefix="selfheal-sandbox-")
        )

        try:
            if source.is_dir():
                destination = sandbox_dir / source.name
                shutil.copytree(source, destination)
                working_directory = destination
            else:
                destination = sandbox_dir / source.name
                shutil.copy2(source, destination)
                working_directory = sandbox_dir

            environment = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            try:
                result = subprocess.run(
                    command,
                    cwd=working_directory,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )

                return SandboxResult(
                    passed=result.returncode == 0,
                    return_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            except subprocess.TimeoutExpired as exc:
                return SandboxResult(
                    passed=False,
                    return_code=-1,
                    stdout=exc.stdout or "",
                    stderr=exc.stderr or "",
                    timed_out=True,
                )

        finally:
            shutil.rmtree(
                sandbox_dir,
                ignore_errors=True,
            )