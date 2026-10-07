import pytest

from selfheal.policy_gate import PolicyGate
from selfheal.risk import RiskLevel


@pytest.fixture
def gate() -> PolicyGate:
    return PolicyGate()


def test_low_risk_verified_candidate_is_accepted(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.LOW,
        verification_passed=True,
        regression_passed=True,
        auto_heal=True,
    )

    assert result.accepted is True
    assert result.requires_human_review is False


def test_medium_risk_verified_candidate_is_accepted(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.MEDIUM,
        verification_passed=True,
        regression_passed=True,
        auto_heal=True,
    )

    assert result.accepted is True
    assert result.requires_human_review is False


def test_high_risk_requires_human_review(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.HIGH,
        verification_passed=True,
        regression_passed=True,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.requires_human_review is True
    assert "HIGH risk" in result.reason


def test_critical_risk_requires_human_review(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.CRITICAL,
        verification_passed=True,
        regression_passed=True,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.requires_human_review is True
    assert "CRITICAL risk" in result.reason


def test_failed_verification_is_rejected(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.LOW,
        verification_passed=False,
        regression_passed=True,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.requires_human_review is False
    assert "verification failed" in result.reason


def test_failed_regression_is_rejected(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.LOW,
        verification_passed=True,
        regression_passed=False,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.requires_human_review is False
    assert "Regression gate failed" in result.reason


def test_auto_heal_disabled_requires_human_review(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.LOW,
        verification_passed=True,
        regression_passed=True,
        auto_heal=False,
    )

    assert result.accepted is False
    assert result.requires_human_review is True
    assert "disabled" in result.reason


def test_policy_does_not_accept_failed_candidate_even_if_low_risk(
    gate: PolicyGate,
):
    result = gate.evaluate(
        risk_level=RiskLevel.LOW,
        verification_passed=False,
        regression_passed=False,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.requires_human_review is False