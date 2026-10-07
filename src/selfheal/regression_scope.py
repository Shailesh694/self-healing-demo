from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileSnapshot:
    """Minimal deterministic snapshot of a repository file."""

    path: str
    content: str


@dataclass(frozen=True)
class ScopeRegressionResult:
    """Result of comparing baseline and candidate file snapshots."""

    passed: bool
    changed_files: tuple[str, ...]
    unexpected_files: tuple[str, ...]


def compare_file_scope(
    baseline: list[FileSnapshot],
    candidate: list[FileSnapshot],
    approved_files: set[str],
) -> ScopeRegressionResult:
    """
    Detect candidate changes outside the approved patch scope.

    This does not judge whether an approved change is correct.
    It only ensures that unrelated files were not modified.
    """

    baseline_by_path = {
        snapshot.path: snapshot
        for snapshot in baseline
    }

    candidate_by_path = {
        snapshot.path: snapshot
        for snapshot in candidate
    }

    all_paths = (
        set(baseline_by_path)
        | set(candidate_by_path)
    )

    changed_files: list[str] = []

    for path in sorted(all_paths):
        baseline_file = baseline_by_path.get(path)
        candidate_file = candidate_by_path.get(path)

        if baseline_file is None or candidate_file is None:
            changed_files.append(path)
            continue

        if baseline_file.content != candidate_file.content:
            changed_files.append(path)

    unexpected_files = sorted(
        set(changed_files) - approved_files
    )

    return ScopeRegressionResult(
        passed=not unexpected_files,
        changed_files=tuple(changed_files),
        unexpected_files=tuple(unexpected_files),
    )