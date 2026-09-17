from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CIResult:
    provider: str
    success: bool
    branch: str
    commit: str
    logs: str


def parse_ci_result(
    payload: dict,
    *,
    provider: str = "generic",
) -> CIResult:
    """
    Normalize a CI result into a common format.
    """

    return CIResult(
        provider=provider,
        success=bool(payload.get("success", False)),
        branch=str(payload.get("branch", "")),
        commit=str(payload.get("commit", "")),
        logs=str(payload.get("logs", "")),
    )