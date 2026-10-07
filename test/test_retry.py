import pytest

from selfheal.retry import (
    MAX_RETRY_ATTEMPTS,
    RetryAttempt,
    RetryController,
)


def test_retry_allows_second_attempt_after_failure():
    controller = RetryController()

    attempts = [
        RetryAttempt(
            attempt=1,
            passed=False,
            error="verification failed",
        ),
    ]

    result = controller.record(attempts)

    assert result.succeeded is False
    assert result.exhausted is False
    assert controller.can_retry(attempts) is True


def test_retry_stops_after_success():
    controller = RetryController()

    attempts = [
        RetryAttempt(
            attempt=1,
            passed=False,
            error="first attempt failed",
        ),
        RetryAttempt(
            attempt=2,
            passed=True,
        ),
    ]

    result = controller.record(attempts)

    assert result.succeeded is True
    assert result.exhausted is False
    assert controller.can_retry(attempts) is False


def test_retry_exhausts_after_three_failures():
    controller = RetryController()

    attempts = [
        RetryAttempt(
            attempt=1,
            passed=False,
            error="failure 1",
        ),
        RetryAttempt(
            attempt=2,
            passed=False,
            error="failure 2",
        ),
        RetryAttempt(
            attempt=3,
            passed=False,
            error="failure 3",
        ),
    ]

    result = controller.record(attempts)

    assert result.succeeded is False
    assert result.exhausted is True
    assert controller.can_retry(attempts) is False


def test_retry_cannot_exceed_three_attempts():
    with pytest.raises(ValueError):
        RetryController(max_attempts=4)


def test_retry_rejects_too_many_recorded_attempts():
    controller = RetryController()

    attempts = [
        RetryAttempt(
            attempt=1,
            passed=False,
        ),
        RetryAttempt(
            attempt=2,
            passed=False,
        ),
        RetryAttempt(
            attempt=3,
            passed=False,
        ),
        RetryAttempt(
            attempt=4,
            passed=False,
        ),
    ]

    with pytest.raises(ValueError):
        controller.record(attempts)


def test_retry_default_limit_is_three():
    assert MAX_RETRY_ATTEMPTS == 3