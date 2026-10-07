from __future__ import annotations

from dataclasses import dataclass

from .analysis.repair import repair_and_verify
from .analysis.report import create_report
from .analysis.history import save_report


@dataclass
class HealingResult:
    status: str
    message: str
    report: object


def heal(
    *,
    file_path: str,
    problem: str,
    confidence: float,
    patch: str,
    project_path: str = ".",
) -> HealingResult:
    """
    Coordinate the complete self-healing process.
    """

    result = repair_and_verify(
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        patch=patch,
        project_path=project_path,
    )

    report = create_report(
        status=result["status"],
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        tests_passed=result.get("tests_passed"),
        message=result.get("test_output", ""),
    )

    save_report(report)

    return HealingResult(
        status=result["status"],
        message=result.get("test_output", ""),
        report=report,
    )