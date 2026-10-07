from __future__ import annotations

import time

from ..git import GitRepository
from .pipeline import run_repair_pipeline
from .rollback import restore_file
from .tests import run_tests


def repair_and_verify(
    *,
    file_path: str,
    problem: str,
    confidence: float,
    patch: str,
    project_path: str = ".",
    git_commit: bool = False,
) -> dict:
    """
    Apply a proposed repair, run tests, and roll back if verification fails.

    With git_commit=True the project must be a Git repository with a clean
    tracked tree. On success the fix is committed on a new `selfheal/fix-*`
    branch; on failure the file is restored and Git is checked for cleanliness.
    """

    repo = None
    if git_commit:
        try:
            repo = GitRepository(project_path)
        except FileNotFoundError:
            repo = None
        if repo is None or not repo.is_repository():
            return {
                "status": "review",
                "reason": "git_commit requires a Git repository",
            }
        if repo.has_tracked_changes():
            return {
                "status": "review",
                "reason": "working tree has uncommitted changes",
            }

    with open(file_path, "r", encoding="utf-8") as file:
        original_content = file.read()

    result = run_repair_pipeline(
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        patch=patch,
        dry_run=False,
    )

    if result["status"] != "validated":
        return result

    test_result = run_tests(
        project_path=project_path,
    )

    if test_result.passed:
        outcome = {
            "status": "repaired",
            "tests_passed": True,
            "test_output": test_result.output,
        }
        if repo is not None:
            branch = f"selfheal/fix-{int(time.time())}"
            b = repo.create_branch(branch)
            c = repo.prepare_commit(f"selfheal: fix {problem[:60]}")
            outcome["git"] = {
                "branch": branch,
                "branch_created": b.success,
                "committed": c.success,
            }
        return outcome

    restore_file(
        file_path=file_path,
        original_content=original_content,
    )

    outcome = {
        "status": "rolled_back",
        "tests_passed": False,
        "test_output": test_result.output,
    }
    if repo is not None:
        outcome["git"] = {
            "clean_after_rollback": not repo.has_tracked_changes()
        }
    return outcome
