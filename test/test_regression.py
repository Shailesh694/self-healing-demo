from selfheal.regression import (
    CheckResult,
    compare_results,
)


def test_no_regression_when_checks_still_pass():
    baseline = [
        CheckResult(
            name="pytest",
            passed=True,
            return_code=0,
            stdout="3 passed",
            stderr="",
        ),
        CheckResult(
            name="compile",
            passed=True,
            return_code=0,
            stdout="",
            stderr="",
        ),
    ]

    candidate = [
        CheckResult(
            name="pytest",
            passed=True,
            return_code=0,
            stdout="4 passed",
            stderr="",
        ),
        CheckResult(
            name="compile",
            passed=True,
            return_code=0,
            stdout="",
            stderr="",
        ),
    ]

    result = compare_results(
        baseline,
        candidate,
    )

    assert result.passed is True
    assert result.regressions == ()


def test_detects_new_failure():
    baseline = [
        CheckResult(
            name="pytest",
            passed=True,
            return_code=0,
            stdout="3 passed",
            stderr="",
        ),
    ]

    candidate = [
        CheckResult(
            name="pytest",
            passed=False,
            return_code=1,
            stdout="",
            stderr="1 failed",
        ),
    ]

    result = compare_results(
        baseline,
        candidate,
    )

    assert result.passed is False
    assert result.regressions == (
        "Regression detected: pytest",
    )


def test_detects_missing_check():
    baseline = [
        CheckResult(
            name="pytest",
            passed=True,
            return_code=0,
            stdout="3 passed",
            stderr="",
        ),
    ]

    candidate = []

    result = compare_results(
        baseline,
        candidate,
    )

    assert result.passed is False
    assert result.regressions == (
        "Missing candidate check: pytest",
    )


def test_existing_baseline_failure_is_not_a_regression():
    baseline = [
        CheckResult(
            name="pytest",
            passed=False,
            return_code=1,
            stdout="",
            stderr="existing failure",
        ),
    ]

    candidate = [
        CheckResult(
            name="pytest",
            passed=False,
            return_code=1,
            stdout="",
            stderr="existing failure",
        ),
    ]

    result = compare_results(
        baseline,
        candidate,
    )

    assert result.passed is True
    assert result.regressions == ()