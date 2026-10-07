from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Incident:
    """
    Normalized representation of a CI/CD failure.

    Different diagnostic tools are converted into this
    common structure before analysis and repair.
    """

    source: str
    code: str
    message: str
    file_path: str | None = None
    line: int | None = None
    column: int | None = None