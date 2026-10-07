from __future__ import annotations

from dataclasses import dataclass


MAX_RETRY_ATTEMPTS = 3


@dataclass(frozen=True)
class RetryAttempt:
    """Record of one remediation attempt."""

    attempt: int
    passed: bool
    error: str | None = None


@dataclass(frozen=True)
class RetryResult:
    """Final result of a bounded remediation retry sequence."""

    succeeded: bool
    attempts: tuple[RetryAttempt, ...]
    exhausted: bool


class RetryController:
    """
    Deterministic retry controller.

    The retry count is hard-limited to three attempts.
    """

    def __init__(
        self,
        max_attempts: int = MAX_RETRY_ATTEMPTS,
    ):
        if max_attempts <= 0:
            raise ValueError(
                "max_attempts must be positive"
            )

        if max_attempts > MAX_RETRY_ATTEMPTS:
            raise ValueError(
                f"max_attempts cannot exceed "
                f"{MAX_RETRY_ATTEMPTS}"
            )

        self.max_attempts = max_attempts

    def record(
        self,
        attempts: list[RetryAttempt],
    ) -> RetryResult:
        """
        Evaluate the current bounded retry history.
        """

        if len(attempts) > self.max_attempts:
            raise ValueError(
                "Retry attempt count exceeds configured limit"
            )

        if any(
            attempt.attempt <= 0
            for attempt in attempts
        ):
            raise ValueError(
                "Attempt numbers must be positive"
            )

        succeeded = any(
            attempt.passed
            for attempt in attempts
        )

        exhausted = (
            not succeeded
            and len(attempts) >= self.max_attempts
        )

        return RetryResult(
            succeeded=succeeded,
            attempts=tuple(attempts),
            exhausted=exhausted,
        )

    def can_retry(
        self,
        attempts: list[RetryAttempt],
    ) -> bool:
        """
        Return whether another attempt is permitted.
        """

        if any(
            attempt.passed
            for attempt in attempts
        ):
            return False

        return len(attempts) < self.max_attempts