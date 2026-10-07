from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RiskAssessment:
    """Deterministic risk assessment for a proposed remediation."""

    level: RiskLevel
    reasons: tuple[str, ...]


def assess_risk(
    *,
    changed_files: int,
    lines_added: int,
    lines_removed: int,
    modifies_dependencies: bool = False,
    modifies_security_code: bool = False,
    modifies_ci_configuration: bool = False,
) -> RiskAssessment:
    """
    Determine remediation risk from deterministic properties.

    AI confidence is intentionally ignored.
    """

    reasons: list[str] = []

    if changed_files <= 0:
        return RiskAssessment(
            level=RiskLevel.CRITICAL,
            reasons=("No changed files detected.",),
        )

    if changed_files > 5:
        reasons.append("Large number of changed files.")

    if lines_added + lines_removed > 200:
        reasons.append("Large patch size.")

    if modifies_dependencies:
        reasons.append("Dependency files are modified.")

    if modifies_security_code:
        reasons.append("Security-sensitive code is modified.")

    if modifies_ci_configuration:
        reasons.append("CI/CD configuration is modified.")

    if (
        modifies_security_code
        or modifies_ci_configuration
        or changed_files > 5
        or lines_added + lines_removed > 200
    ):
        return RiskAssessment(
            level=RiskLevel.HIGH,
            reasons=tuple(reasons),
        )

    if modifies_dependencies or lines_added + lines_removed > 50:
        return RiskAssessment(
            level=RiskLevel.MEDIUM,
            reasons=tuple(reasons),
        )

    if not reasons:
        reasons.append(
            "Small scoped source change."
        )

    return RiskAssessment(
        level=RiskLevel.LOW,
        reasons=tuple(reasons),
    )