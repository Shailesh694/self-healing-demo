from __future__ import annotations

from .executor import apply_patch
from .generator import generate_candidate
from .validator import validate_candidate


def run_repair_pipeline(
    *,
    file_path: str,
    problem: str,
    confidence: float,
    patch: str | None,
    dry_run: bool = True,
) -> dict:
    """
    Run the complete analysis-to-repair pipeline.
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
        return {
            "status": "rejected",
            "candidate": candidate,
            "errors": validation.errors,
        }

    applied = apply_patch(
        file_path=candidate.file_path,
        patch=candidate.patch or "",
        dry_run=dry_run,
    )

    return {
        "status": "validated",
        "applied": applied and not dry_run,
        "dry_run": dry_run,
        "candidate": candidate,
    }