from __future__ import annotations

from .fix import FixCandidate, create_candidate


def generate_candidate(
    *,
    file_path: str,
    problem: str,
    confidence: float,
    patch: str | None = None,
) -> FixCandidate:
    """
    Generate a structured repair candidate from an analyzed problem.

    This function proposes a repair but does not modify any files.
    """

    description = (
        f"Proposed repair for {file_path}: {problem}"
    )

    return create_candidate(
        file_path=file_path,
        description=description,
        confidence=confidence,
        patch=patch,
    )