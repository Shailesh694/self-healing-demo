from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RepairReport:
    status: str
    file_path: str
    problem: str
    confidence: float
    tests_passed: bool | None = None
    message: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )


def create_report(
    *,
    status: str,
    file_path: str,
    problem: str,
    confidence: float,
    tests_passed: bool | None = None,
    message: str = "",
) -> RepairReport:
    return RepairReport(
        status=status,
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        tests_passed=tests_passed,
        message=message,
    )