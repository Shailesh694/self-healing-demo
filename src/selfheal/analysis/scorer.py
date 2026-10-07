from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAssessment:
    tier: str
    files_changed: int
    lines_changed: int
    security_sensitive: bool


SECURITY_SENSITIVE_PATHS = (
    ".github/",
    "auth",
    "security",
    "secrets",
    "credentials",
    ".env",
)


def assess_risk(
    *,
    files_changed: int,
    lines_changed: int,
    changed_paths: list[str],
) -> RiskAssessment:
    security_sensitive = any(
        any(marker in path.lower() for marker in SECURITY_SENSITIVE_PATHS)
        for path in changed_paths
    )

    if security_sensitive:
        tier = "CRITICAL"
    elif files_changed >= 5 or lines_changed >= 200:
        tier = "HIGH"
    elif files_changed >= 2 or lines_changed >= 50:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return RiskAssessment(
        tier=tier,
        files_changed=files_changed,
        lines_changed=lines_changed,
        security_sensitive=security_sensitive,
    )