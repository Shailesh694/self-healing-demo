from selfheal.remediation_controller import (
    RemediationController,
)
from selfheal.risk import RiskLevel


def test_successful_attempt_is_accepted():
    controller = RemediationController()

    attempt = controller.create_attempt(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level=RiskLevel.LOW,
        auto_heal=True,
    )

    result = controller.evaluate(
        attempts=[attempt],
        risk_level=RiskLevel.LOW,
        auto_heal=True,
    )

    assert result.accepted is True
    assert result.requires_human_review is False
    assert result.exhausted is False


def test_failed_attempt_can_retry():
    controller = RemediationController()

    attempt = controller.create_attempt(
        attempt=1,
        verification_passed=False,
        regression_passed=True,
        risk_level=RiskLevel.LOW,
        auto_heal=True,
        error="pytest failed",
    )

    result = controller.evaluate(
        attempts=[attempt],
        risk_level=RiskLevel.LOW,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.exhausted is False
    assert result.requires_human_review is False


def test_three_failed_attempts_exhaust_retry():
    controller = RemediationController()

    attempts = []

    for number in range(1, 4):
        attempts.append(
            controller.create_attempt(
                attempt=number,
                verification_passed=False,
                regression_passed=True,
                risk_level=RiskLevel.LOW,
                auto_heal=True,
                error=f"failure {number}",
            )
        )

    result = controller.evaluate(
        attempts=attempts,
        risk_level=RiskLevel.LOW,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.exhausted is True


def test_high_risk_requires_human_review():
    controller = RemediationController()

    attempt = controller.create_attempt(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level=RiskLevel.HIGH,
        auto_heal=True,
    )

    result = controller.evaluate(
        attempts=[attempt],
        risk_level=RiskLevel.HIGH,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.requires_human_review is True
    assert result.exhausted is False


def test_failed_regression_cannot_be_accepted():
    controller = RemediationController()

    attempt = controller.create_attempt(
        attempt=1,
        verification_passed=True,
        regression_passed=False,
        risk_level=RiskLevel.LOW,
        auto_heal=True,
        error="regression detected",
    )

    result = controller.evaluate(
        attempts=[attempt],
        risk_level=RiskLevel.LOW,
        auto_heal=True,
    )

    assert result.accepted is False
    assert result.exhausted is False


def test_later_success_after_failure_is_accepted():
    controller = RemediationController()

    first = controller.create_attempt(
        attempt=1,
        verification_passed=False,
        regression_passed=True,
        risk_level=RiskLevel.LOW,
        auto_heal=True,
        error="first verification failed",
    )

    second = controller.create_attempt(
        attempt=2,
        verification_passed=True,
        regression_passed=True,
        risk_level=RiskLevel.LOW,
        auto_heal=True,
    )

    result = controller.evaluate(
        attempts=[first, second],
        risk_level=RiskLevel.LOW,
        auto_heal=True,
    )

    assert result.accepted is True
    assert result.requires_human_review is False
    assert result.exhausted is False