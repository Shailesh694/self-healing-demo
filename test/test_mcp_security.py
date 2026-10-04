from pathlib import Path

import pytest

from selfheal.mcp.server import mcp_server
from selfheal.mcp.tools import (
    analyze_scope,
    generate_patch,
    inspect_incident,
    rollback,
    run_remediation,
    scan_repository,
    verify_patch,
)


def test_scan_repository_rejects_empty_path():
    with pytest.raises(ValueError, match="repository_path"):
        scan_repository("")


def test_scan_repository_rejects_missing_path(
    tmp_path: Path,
):
    missing = tmp_path / "does-not-exist"

    with pytest.raises(FileNotFoundError):
        scan_repository(str(missing))


def test_scan_repository_rejects_file_path(
    tmp_path: Path,
):
    target = tmp_path / "app.py"

    target.write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not a directory"):
        scan_repository(str(target))


def test_inspect_incident_rejects_empty_fingerprint():
    with pytest.raises(
        ValueError,
        match="fingerprint",
    ):
        inspect_incident("")


def test_analyze_scope_rejects_empty_repository():
    with pytest.raises(
        ValueError,
        match="repository_path",
    ):
        analyze_scope(
            "",
            "app.py",
        )


def test_analyze_scope_rejects_empty_file_path(
    tmp_path: Path,
):
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(
        ValueError,
        match="file_path",
    ):
        analyze_scope(
            str(repository),
            "",
        )


def test_analyze_scope_rejects_invalid_line(
    tmp_path: Path,
):
    repository = tmp_path / "repo"
    repository.mkdir()

    (repository / "app.py").write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="line",
    ):
        analyze_scope(
            str(repository),
            "app.py",
            line=0,
        )


def test_analyze_scope_rejects_unknown_file(
    tmp_path: Path,
):
    repository = tmp_path / "repo"
    repository.mkdir()

    (repository / "app.py").write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError):
        analyze_scope(
            str(repository),
            "missing.py",
        )


def test_generate_patch_rejects_empty_file_path():
    with pytest.raises(
        ValueError,
        match="file_path",
    ):
        generate_patch(
            file_path="",
            problem="broken function",
            confidence=0.9,
        )


def test_generate_patch_rejects_empty_problem():
    with pytest.raises(
        ValueError,
        match="problem",
    ):
        generate_patch(
            file_path="app.py",
            problem="",
            confidence=0.9,
        )


def test_verify_patch_rejects_empty_file_path():
    with pytest.raises(
        ValueError,
        match="file_path",
    ):
        verify_patch(
            file_path="",
            confidence=0.9,
            patch="some patch",
        )


def test_verify_patch_rejects_invalid_confidence():
    result = verify_patch(
        file_path="app.py",
        confidence=1.5,
        patch="some patch",
    )

    assert result["valid"] is False
    assert "Confidence must be between 0.0 and 1.0" in result["errors"]


def test_verify_patch_rejects_negative_confidence():
    result = verify_patch(
        file_path="app.py",
        confidence=-0.1,
        patch="some patch",
    )

    assert result["valid"] is False
    assert "Confidence must be between 0.0 and 1.0" in result["errors"]

def test_run_remediation_rejects_zero_attempt():
    with pytest.raises(
        ValueError,
        match="attempt",
    ):
        run_remediation(
            attempt=0,
            verification_passed=True,
            regression_passed=True,
            risk_level="LOW",
            auto_heal=True,
        )


def test_run_remediation_rejects_negative_attempt():
    with pytest.raises(
        ValueError,
        match="attempt",
    ):
        run_remediation(
            attempt=-1,
            verification_passed=True,
            regression_passed=True,
            risk_level="LOW",
            auto_heal=True,
        )


def test_run_remediation_rejects_empty_risk_level():
    with pytest.raises(
        ValueError,
        match="risk_level",
    ):
        run_remediation(
            attempt=1,
            verification_passed=True,
            regression_passed=True,
            risk_level="",
            auto_heal=True,
        )


def test_run_remediation_rejects_unknown_risk_level():
    with pytest.raises(
        ValueError,
        match="risk_level",
    ):
        run_remediation(
            attempt=1,
            verification_passed=True,
            regression_passed=True,
            risk_level="UNKNOWN",
            auto_heal=True,
        )


def test_rollback_returns_deterministic_decision():
    result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "VERIFICATION_FAILURE"


def test_rollback_does_not_execute_git_operation():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is False
    assert result["reason"] is None


def test_mcp_security_tools_are_registered():
    tools = mcp_server._tool_manager.list_tools()

    names = {
        tool.name
        for tool in tools
    }

    expected = {
        "scan_repository",
        "get_incidents",
        "inspect_incident",
        "analyze_scope",
        "generate_patch",
        "verify_patch",
        "run_remediation",
        "get_remediation_status",
        "rollback",
    }

    assert expected.issubset(names)