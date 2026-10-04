from selfheal.regression import CheckResult
from selfheal.regression_gate import RegressionGate
from selfheal.regression_scope import FileSnapshot


def check(
    name: str,
    passed: bool,
) -> CheckResult:
    return CheckResult(
        name=name,
        passed=passed,
        return_code=0 if passed else 1,
        stdout="",
        stderr="",
    )


def snapshot(
    path: str,
    content: str,
) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        content=content,
    )


def test_gate_passes_for_safe_candidate():
    gate = RegressionGate()

    result = gate.evaluate(
        baseline_checks=[
            check("pytest", True),
            check("compile", True),
        ],
        candidate_checks=[
            check("pytest", True),
            check("compile", True),
        ],
        baseline_files=[
            snapshot("app.py", "old"),
        ],
        candidate_files=[
            snapshot("app.py", "new"),
        ],
        approved_files={"app.py"},
    )

    assert result.passed is True
    assert result.reasons == ()


def test_gate_rejects_verification_regression():
    gate = RegressionGate()

    result = gate.evaluate(
        baseline_checks=[
            check("pytest", True),
        ],
        candidate_checks=[
            check("pytest", False),
        ],
        baseline_files=[
            snapshot("app.py", "old"),
        ],
        candidate_files=[
            snapshot("app.py", "new"),
        ],
        approved_files={"app.py"},
    )

    assert result.passed is False
    assert "Regression detected: pytest" in result.reasons


def test_gate_rejects_unapproved_file_change():
    gate = RegressionGate()

    result = gate.evaluate(
        baseline_checks=[
            check("pytest", True),
        ],
        candidate_checks=[
            check("pytest", True),
        ],
        baseline_files=[
            snapshot(
                "app.py",
                "old",
            ),
            snapshot(
                "config.py",
                "safe",
            ),
        ],
        candidate_files=[
            snapshot(
                "app.py",
                "new",
            ),
            snapshot(
                "config.py",
                "changed",
            ),
        ],
        approved_files={"app.py"},
    )

    assert result.passed is False
    assert (
        "Unexpected file change: config.py"
        in result.reasons
    )


def test_gate_rejects_both_failure_types():
    gate = RegressionGate()

    result = gate.evaluate(
        baseline_checks=[
            check("pytest", True),
        ],
        candidate_checks=[
            check("pytest", False),
        ],
        baseline_files=[
            snapshot(
                "app.py",
                "old",
            ),
            snapshot(
                "config.py",
                "safe",
            ),
        ],
        candidate_files=[
            snapshot(
                "app.py",
                "new",
            ),
            snapshot(
                "config.py",
                "changed",
            ),
        ],
        approved_files={"app.py"},
    )

    assert result.passed is False

    assert (
        "Regression detected: pytest"
        in result.reasons
    )

    assert (
        "Unexpected file change: config.py"
        in result.reasons
    )


def test_existing_baseline_failure_does_not_fail_gate_by_itself():
    gate = RegressionGate()

    result = gate.evaluate(
        baseline_checks=[
            check("pytest", False),
        ],
        candidate_checks=[
            check("pytest", False),
        ],
        baseline_files=[
            snapshot("app.py", "old"),
        ],
        candidate_files=[
            snapshot("app.py", "new"),
        ],
        approved_files={"app.py"},
    )

    assert result.passed is True
    assert result.reasons == ()