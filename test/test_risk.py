import pytest

from selfheal.risk import (
    RiskLevel,
    assess_risk,
)


def test_small_source_change_is_low_risk():
    result = assess_risk(
        changed_files=1,
        lines_added=5,
        lines_removed=3,
    )

    assert result.level == RiskLevel.LOW
    assert result.reasons == (
        "Small scoped source change.",
    )


def test_medium_patch_is_medium_risk():
    result = assess_risk(
        changed_files=1,
        lines_added=30,
        lines_removed=25,
    )

    assert result.level == RiskLevel.MEDIUM
    assert "Small scoped source change." not in result.reasons


def test_dependency_change_is_medium_risk():
    result = assess_risk(
        changed_files=1,
        lines_added=5,
        lines_removed=2,
        modifies_dependencies=True,
    )

    assert result.level == RiskLevel.MEDIUM
    assert (
        "Dependency files are modified."
        in result.reasons
    )


def test_security_change_is_high_risk():
    result = assess_risk(
        changed_files=1,
        lines_added=5,
        lines_removed=2,
        modifies_security_code=True,
    )

    assert result.level == RiskLevel.HIGH
    assert (
        "Security-sensitive code is modified."
        in result.reasons
    )


def test_ci_change_is_high_risk():
    result = assess_risk(
        changed_files=1,
        lines_added=5,
        lines_removed=2,
        modifies_ci_configuration=True,
    )

    assert result.level == RiskLevel.HIGH
    assert (
        "CI/CD configuration is modified."
        in result.reasons
    )


def test_large_patch_is_high_risk():
    result = assess_risk(
        changed_files=6,
        lines_added=100,
        lines_removed=120,
    )

    assert result.level == RiskLevel.HIGH
    assert (
        "Large number of changed files."
        in result.reasons
    )
    assert (
        "Large patch size."
        in result.reasons
    )


def test_zero_changed_files_is_critical():
    result = assess_risk(
        changed_files=0,
        lines_added=0,
        lines_removed=0,
    )

    assert result.level == RiskLevel.CRITICAL
    assert result.reasons == (
        "No changed files detected.",
    )


def test_risk_does_not_depend_on_ai_confidence():
    """
    The risk API has no AI-confidence parameter.
    Risk is determined entirely from deterministic inputs.
    """

    result_a = assess_risk(
        changed_files=1,
        lines_added=5,
        lines_removed=3,
    )

    result_b = assess_risk(
        changed_files=1,
        lines_added=5,
        lines_removed=3,
    )

    assert result_a == result_b