from __future__ import annotations

from dataclasses import dataclass

from .analysis.generator import generate_candidate
from .analysis.validator import validate_candidate


@dataclass
class RepairPlan:
    file_path: str
    problem: str
    confidence: float
    patch: str


def build_repair_plan(
    *,
    file_path: str,
    problem: str,
    confidence: float,
    patch: str,
) -> RepairPlan:
    """
    Build and validate a repair plan before execution.
    """

    candidate = generate_candidate(
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        patch=patch,
    )

    validation = validate_candidate(
        file_path=candidate.file_path,
        confidence=candidate.confidence,
        patch=candidate.patch,
    )

    if not validation.valid:
        raise ValueError(
            "; ".join(validation.errors)
        )

    return RepairPlan(
        file_path=candidate.file_path,
        problem=problem,
        confidence=confidence,
        patch=patch,
    )