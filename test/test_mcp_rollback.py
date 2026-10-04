from selfheal.mcp.server import mcp_server
from selfheal.mcp.tools import rollback


def test_rollback_required_for_verification_failure():
    result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "VERIFICATION_FAILURE"


def test_rollback_required_for_regression_failure():
    result = rollback(
        verification_passed=True,
        regression_passed=False,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "REGRESSION_FAILURE"


def test_rollback_required_when_retries_exhausted():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=True,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "RETRY_EXHAUSTED"


def test_rollback_required_for_policy_rejection():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "POLICY_REJECTION"


def test_rollback_not_required_when_all_checks_pass():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is False
    assert result["reason"] is None


def test_verification_failure_has_priority():
    result = rollback(
        verification_passed=False,
        regression_passed=False,
        retry_exhausted=True,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "VERIFICATION_FAILURE"


def test_mcp_server_registers_rollback_tool():
    tools = mcp_server._tool_manager.list_tools()

    names = {
        tool.name
        for tool in tools
    }

    assert "rollback" in names