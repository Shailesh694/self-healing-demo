from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .events import repair_completed, repair_started
from .orchestrator import heal


@dataclass
class HandlerResult:
    status: str
    incident_id: str
    message: str


def handle_failure(
    *,
    incident_id: str,
    file_path: str,
    problem: str,
    confidence: float,
    patch: str,
    project_path: str = ".",
) -> HandlerResult:
    """
    Handle a CI/CD failure and pass it through the
    self-healing workflow.
    """

    repair_started(incident_id)

    result = heal(
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        patch=patch,
        project_path=project_path,
    )

    repair_completed(
        incident_id,
        result.status,
    )

    return HandlerResult(
        status=result.status,
        incident_id=incident_id,
        message=result.message,
    )