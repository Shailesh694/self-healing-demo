from selfheal.mcp import tools


def test_run_agent_pipeline_rejects_empty_incident():
    try:
        tools.run_agent_pipeline(
            incident="",
            repository_context="app.py",
        )
    except ValueError as exc:
        assert str(exc) == "incident cannot be empty"
    else:
        raise AssertionError("Expected ValueError")


def test_run_agent_pipeline_rejects_empty_repository_context():
    try:
        tools.run_agent_pipeline(
            incident="NameError",
            repository_context="",
        )
    except ValueError as exc:
        assert str(exc) == "repository_context cannot be empty"
    else:
        raise AssertionError("Expected ValueError")

from selfheal.mcp.server import mcp_server


def test_mcp_server_registers_agent_pipeline():
    registered = mcp_server._tool_manager.list_tools()

    names = {
        tool.name
        for tool in registered
    }

    assert "run_agent_pipeline" in names