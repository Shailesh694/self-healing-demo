from selfheal.mcp.tools import (
    run_regression_gate,
    run_remediation,
)


def check(
    name: str,
    passed: bool,
) -> dict:
    return {
        "name": name,
        "passed": passed,
        "return_code": 0 if passed else 1,
        "stdout": "passed" if passed else "",
        "stderr": "" if passed else "failed",
    }


def file(
    path: str,
    content: str,
) -> dict:
    return {
        "path": path,
        "content": content,
    }


def test_mcp_regression_gate_accepts_valid_candidate():
    result = run_regression_gate(
        baseline_checks=[check("pytest", True)],
        candidate_checks=[check("pytest", True)],
        baseline_files=[file("app.py", "old")],
        candidate_files=[file("app.py", "new")],
        approved_files=["app.py"],
    )

    assert result["passed"] is True
    assert result["reasons"] == []


def test_mcp_regression_gate_rejects_regression():
    result = run_regression_gate(
        baseline_checks=[check("pytest", True)],
        candidate_checks=[check("pytest", False)],
        baseline_files=[file("app.py", "old")],
        candidate_files=[file("app.py", "new")],
        approved_files=["app.py"],
    )

    assert result["passed"] is False
    assert "Regression detected: pytest" in result["reasons"]


def test_mcp_regression_gate_rejects_unapproved_change():
    result = run_regression_gate(
        baseline_checks=[check("pytest", True)],
        candidate_checks=[check("pytest", True)],
        baseline_files=[
            file("app.py", "old"),
            file("config.py", "old"),
        ],
        candidate_files=[
            file("app.py", "new"),
            file("config.py", "changed"),
        ],
        approved_files=["app.py"],
    )

    assert result["passed"] is False
    assert (
        "Unexpected file change: config.py"
        in result["reasons"]
    )

def test_run_remediation_uses_actual_regression_gate():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
        regression_inputs={
            "baseline_checks": [
                {
                    "name": "pytest",
                    "passed": True,
                    "return_code": 0,
                    "stdout": "10 passed",
                    "stderr": "",
                },
            ],
            "candidate_checks": [
                {
                    "name": "pytest",
                    "passed": False,
                    "return_code": 1,
                    "stdout": "",
                    "stderr": "failed",
                },
            ],
            "baseline_files": [
                {
                    "path": "app.py",
                    "content": "old",
                },
            ],
            "candidate_files": [
                {
                    "path": "app.py",
                    "content": "new",
                },
            ],
            "approved_files": [
                "app.py",
            ],
        },
    )

    assert result["accepted"] is False
    assert result["status"] == "rejected"
    assert result["attempts"][0]["regression_passed"] is False
    assert "Regression detected: pytest" in (
        result["attempts"][0]["error"]
    )