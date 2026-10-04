from selfheal.rollback_controller import (
    RollbackController,
    RollbackReason,
)


def test_successful_candidate_does_not_require_rollback():
    controller = RollbackController()

    result = controller.evaluate(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result.required is False
    assert result.reason is None


def test_verification_failure_requires_rollback():
    controller = RollbackController()

    result = controller.evaluate(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result.required is True
    assert result.reason == (
        RollbackReason.VERIFICATION_FAILURE
    )


def test_regression_failure_requires_rollback():
    controller = RollbackController()

    result = controller.evaluate(
        verification_passed=True,
        regression_passed=False,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result.required is True
    assert result.reason == (
        RollbackReason.REGRESSION_FAILURE
    )


def test_exhausted_retries_require_rollback():
    controller = RollbackController()

    result = controller.evaluate(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=True,
        policy_accepted=True,
    )

    assert result.required is True
    assert result.reason == (
        RollbackReason.RETRY_EXHAUSTED
    )


def test_policy_rejection_requires_rollback():
    controller = RollbackController()

    result = controller.evaluate(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=False,
    )

    assert result.required is True
    assert result.reason == (
        RollbackReason.POLICY_REJECTION
    )


def test_verification_failure_has_priority():
    controller = RollbackController()

    result = controller.evaluate(
        verification_passed=False,
        regression_passed=False,
        retry_exhausted=True,
        policy_accepted=False,
    )

    assert result.required is True
    assert result.reason == (
        RollbackReason.VERIFICATION_FAILURE
    )