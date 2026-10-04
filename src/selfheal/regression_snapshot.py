from __future__ import annotations

from pathlib import Path

from .regression import CheckResult
from .regression_scope import FileSnapshot


def snapshot_files(
    repository_path: str,
) -> list[FileSnapshot]:
    """
    Capture deterministic text snapshots of tracked repository files.

    This is read-only.
    """

    root = Path(repository_path).resolve()

    if not root.exists():
        raise FileNotFoundError(
            f"Repository path does not exist: {root}"
        )

    snapshots: list[FileSnapshot] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        if ".git" in path.parts:
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        snapshots.append(
            FileSnapshot(
                path=path.relative_to(root).as_posix(),
                content=content,
            )
        )

    return snapshots


def check_result_from_verification(
    *,
    name: str,
    passed: bool,
    return_code: int,
    output: str,
) -> CheckResult:
    """
    Convert an existing verification result into
    the deterministic regression check format.
    """

    return CheckResult(
        name=name,
        passed=passed,
        return_code=return_code,
        stdout=output,
        stderr="",
    )