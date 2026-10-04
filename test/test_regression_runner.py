from selfheal.regression import CheckResult
from selfheal.regression_runner import evaluate_regression
from selfheal.regression_scope import FileSnapshot

from pathlib import Path

from selfheal.regression_runner import (
    capture_regression_baseline,
    capture_regression_candidate,
)



def make_check(
    name: str,
    passed: bool,
) -> CheckResult:
    return CheckResult(
        name=name,
        passed=passed,
        return_code=0 if passed else 1,
        stdout="passed" if passed else "",
        stderr="" if passed else "failed",
    )


def make_file(
    path: str,
    content: str,
) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        content=content,
    )


def test_regression_runner_accepts_valid_candidate():
    baseline_checks = [
        make_check("pytest", True),
    ]
    candidate_checks = [
        make_check("pytest", True),
    ]

    baseline_files = [
        make_file("app.py", "print('old')\n"),
    ]
    candidate_files = [
        make_file("app.py", "print('new')\n"),
    ]

    result = evaluate_regression(
        baseline_checks=baseline_checks,
        candidate_checks=candidate_checks,
        baseline_files=baseline_files,
        candidate_files=candidate_files,
        approved_files={"app.py"},
    )

    assert result.passed is True
    assert result.reasons == ()


def test_regression_runner_rejects_test_regression():
    baseline_checks = [
        make_check("pytest", True),
    ]
    candidate_checks = [
        make_check("pytest", False),
    ]

    baseline_files = [
        make_file("app.py", "old"),
    ]
    candidate_files = [
        make_file("app.py", "new"),
    ]

    result = evaluate_regression(
        baseline_checks=baseline_checks,
        candidate_checks=candidate_checks,
        baseline_files=baseline_files,
        candidate_files=candidate_files,
        approved_files={"app.py"},
    )

    assert result.passed is False
    assert "Regression detected: pytest" in result.reasons


def test_regression_runner_rejects_unapproved_file_change():
    baseline_checks = [
        make_check("pytest", True),
    ]
    candidate_checks = [
        make_check("pytest", True),
    ]

    baseline_files = [
        make_file("app.py", "old"),
        make_file("config.py", "old"),
    ]
    candidate_files = [
        make_file("app.py", "new"),
        make_file("config.py", "changed"),
    ]

    result = evaluate_regression(
        baseline_checks=baseline_checks,
        candidate_checks=candidate_checks,
        baseline_files=baseline_files,
        candidate_files=candidate_files,
        approved_files={"app.py"},
    )

    assert result.passed is False
    assert "Unexpected file change: config.py" in result.reasons



def test_capture_baseline_captures_files_and_tests(
    tmp_path: Path,
):
    test_file = tmp_path / "app.py"
    test_file.write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    check, files = capture_regression_baseline(
        repository_path=str(tmp_path),
        test_command=[
            "python",
            "-c",
            "print('baseline')",
        ],
    )

    assert check.name == "pytest"
    assert check.passed is True
    assert check.return_code == 0
    assert "baseline" in check.stdout

    assert len(files) == 1
    assert files[0].path == "app.py"


def test_capture_candidate_captures_current_state(
    tmp_path: Path,
):
    test_file = tmp_path / "app.py"
    test_file.write_text(
        "value = 2\n",
        encoding="utf-8",
    )

    check, files = capture_regression_candidate(
        repository_path=str(tmp_path),
        test_command=[
            "python",
            "-c",
            "print('candidate')",
        ],
    )

    assert check.passed is True
    assert "candidate" in check.stdout
    assert files[0].content == "value = 2\n"