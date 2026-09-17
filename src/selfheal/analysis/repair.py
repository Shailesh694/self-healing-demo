from __future__ import annotations

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
) -> dict:
    """
    Apply a proposed repair, run tests, and roll back if verification fails.
    """

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
        return {
            "status": "repaired",
            "tests_passed": True,
            "test_output": test_result.output,
        }

    restore_file(
        file_path=file_path,
        original_content=original_content,
    )

    return {
        "status": "rolled_back",
        "tests_passed": False,
        "test_output": test_result.output,
    }