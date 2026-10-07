from selfheal.mcp.server import mcp_server
import pytest
from selfheal.mcp.tools import (
    get_remediation_status,
    run_remediation,
)


@pytest.fixture(autouse=True)
def reset_remediation_state():
    from selfheal.mcp import tools

    tools._remediation_state["status"] = "idle"
    tools._remediation_state["result"] = None
    yield
    tools._remediation_state["status"] = "idle"
    tools._remediation_state["result"] = None

def test_remediation_status_starts_with_idle_state():
    result = get_remediation_status()

    assert result["status"] == "idle"
    assert result["result"] is None


def test_run_remediation_accepts_successful_attempt():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
    )

    assert result["accepted"] is True
    assert result["requires_human_review"] is False
    assert result["exhausted"] is False
    assert result["status"] == "accepted"

    assert len(result["attempts"]) == 1

    attempt = result["attempts"][0]

    assert attempt["attempt"] == 1
    assert attempt["verification_passed"] is True
    assert attempt["regression_passed"] is True
    assert attempt["policy"]["accepted"] is True


def test_run_remediation_rejects_failed_verification():
    result = run_remediation(
        attempt=1,
        verification_passed=False,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
        error="Verification failed",
    )

    assert result["accepted"] is False
    assert result["status"] == "rejected"

    attempt = result["attempts"][0]

    assert attempt["verification_passed"] is False
    assert attempt["error"] == "Verification failed"
    assert attempt["policy"]["accepted"] is False


def test_run_remediation_requires_human_review_for_high_risk():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="HIGH",
        auto_heal=True,
    )

    assert result["accepted"] is False
    assert result["requires_human_review"] is True
    assert result["status"] == "human_review_required"


def test_run_remediation_rejects_invalid_attempt():
    try:
        run_remediation(
            attempt=0,
            verification_passed=True,
            regression_passed=True,
            risk_level="LOW",
            auto_heal=True,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "attempt" in str(exc)


def test_run_remediation_rejects_invalid_risk_level():
    try:
        run_remediation(
            attempt=1,
            verification_passed=True,
            regression_passed=True,
            risk_level="UNKNOWN",
            auto_heal=True,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "risk_level" in str(exc)


def test_get_remediation_status_returns_latest_result():
    run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
    )

    result = get_remediation_status()

    assert result["status"] == "accepted"
    assert result["result"] is not None
    assert result["result"]["accepted"] is True


def test_mcp_server_registers_remediation_tools():
    tools = mcp_server._tool_manager.list_tools()

    names = {
        tool.name
        for tool in tools
    }

    assert "run_remediation" in names
    assert "get_remediation_status" in names

def test_run_remediation_requires_rollback_on_regression_failure():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=False,
        risk_level="LOW",
        auto_heal=True,
    )

    assert result["accepted"] is False
    assert result["status"] == "rejected"

def test_verify_repair_in_sandbox():
    from pathlib import Path
    from selfheal.mcp.tools import verify_repair_in_sandbox

    import sys
    import tempfile

    repository = Path(tempfile.mkdtemp(dir=Path.cwd()))
    (repository / "test_ok.py").write_text("def test_ok():\n    assert True\n")

    try:
        result = verify_repair_in_sandbox(
            repository_path=str(repository),
            command=[sys.executable, "-m", "pytest", ".", "-q"],
        )
    finally:
        import shutil
        shutil.rmtree(repository, ignore_errors=True)

    assert result["passed"] is True
    assert result["return_code"] == 0
    assert "1 passed" in result["stdout"]
    assert result["timed_out"] is False


def test_verify_repair_in_sandbox_rejects_arbitrary_commands():
    import pytest
    from selfheal.mcp.tools import verify_repair_in_sandbox

    for bad in (
        ["python", "-c", "print(1)"],
        ["rm", "-rf", "."],
        ["python", "-m", "pytest", "-p", "evil"],
        ["python", "-m", "pytest", "; rm -rf /"],
        ["python", "-m", "http.server"],
    ):
        with pytest.raises(ValueError):
            verify_repair_in_sandbox(repository_path=".", command=bad)

def test_mcp_server_registers_sandbox_verification_tool():
    tools = mcp_server._tool_manager._tools

    assert "verify_repair_in_sandbox" in tools

def test_run_remediation_rejects_sandbox_failure(tmp_path):
    import sys
    from selfheal.mcp.tools import run_remediation

    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
        sandbox_inputs={
            "repository_path": str(tmp_path),
            "command": [
                sys.executable,
                "-m",
                "pytest",
                ".",
                "-q",
            ],
        },
    )

    assert result["accepted"] is False
    assert result["status"] == "rejected"
    assert result["attempts"][0]["verification_passed"] is False
    assert "Sandbox verification failed" in result["attempts"][0]["error"]