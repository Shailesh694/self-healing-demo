from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FixCandidate:
    file_path: str
    description: str
    confidence: float
    patch: str | None = None


def create_candidate(
    *,
    file_path: str,
    description: str,
    confidence: float,
    patch: str | None = None,
) -> FixCandidate:
    """
    Create a proposed fix without applying it.

    The system must keep diagnosis and modification separate so
    that fixes can be reviewed and validated before execution.
    """
    if not file_path:
        raise ValueError("file_path cannot be empty")

    if not description:
        raise ValueError("description cannot be empty")

    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")

    return FixCandidate(
        file_path=file_path,
        description=description,
        confidence=confidence,
        patch=patch,
    )