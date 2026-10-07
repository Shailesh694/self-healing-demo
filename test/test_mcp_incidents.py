import pytest

from selfheal.incidents.fingerprint import IncidentFingerprinter
from selfheal.mcp import tools
from selfheal.models import Incident
from selfheal.runtime import incident_manager


def reset_incident_store():
    incident_manager._incidents.clear()
    tools.incident_manager = incident_manager


@pytest.fixture(autouse=True)
def restore_incident_manager():
    reset_incident_store()
    yield
    reset_incident_store()


def create_incident() -> Incident:
    return Incident(
        source="pytest",
        code="PYTEST_FAILURE",
        message="AssertionError: expected 1",
        file_path="app.py",
        line=10,
        column=4,
    )


def test_get_incidents_returns_open_incidents():
    reset_incident_store()

    incident = create_incident()

    tools.incident_manager.create(
        incident
    )

    result = tools.get_incidents()

    assert result["count"] == 1
    assert len(result["incidents"]) == 1

    returned = result["incidents"][0]

    assert returned["source"] == "pytest"
    assert returned["code"] == "PYTEST_FAILURE"
    assert returned["file_path"] == "app.py"
    assert returned["line"] == 10
    assert returned["column"] == 4
    assert returned["status"] == "open"


def test_get_incidents_returns_fingerprint():
    reset_incident_store()

    incident = create_incident()

    tools.incident_manager.create(
        incident
    )

    result = tools.get_incidents()

    expected = (
        IncidentFingerprinter()
        .fingerprint(incident)
    )

    assert (
        result["incidents"][0]["fingerprint"]
        == expected
    )


def test_get_incidents_excludes_closed_incidents():
    reset_incident_store()

    incident = create_incident()

    record = tools.incident_manager.create(
        incident
    )

    tools.incident_manager.close(record)

    result = tools.get_incidents()

    assert result["count"] == 0
    assert result["incidents"] == []


def test_inspect_incident_returns_matching_incident():
    reset_incident_store()

    incident = create_incident()

    tools.incident_manager.create(
        incident
    )

    fingerprint = (
        IncidentFingerprinter()
        .fingerprint(incident)
    )

    result = tools.inspect_incident(
        fingerprint
    )

    assert result["found"] is True
    assert result["fingerprint"] == fingerprint
    assert result["status"] == "open"

    assert (
        result["incident"]["source"]
        == "pytest"
    )

    assert (
        result["incident"]["message"]
        == "AssertionError: expected 1"
    )


def test_inspect_incident_returns_not_found():
    reset_incident_store()

    result = tools.inspect_incident(
        "does-not-exist"
    )

    assert result["found"] is False
    assert (
        result["fingerprint"]
        == "does-not-exist"
    )
    assert (
        result["error"]
        == "Incident not found"
    )


def test_inspect_incident_rejects_empty_fingerprint():
    reset_incident_store()

    try:
        tools.inspect_incident("")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "fingerprint" in str(exc)


def test_mcp_server_registers_incident_tools():
    from selfheal.mcp.server import (
        mcp_server,
    )

    tools_list = (
        mcp_server
        ._tool_manager
        .list_tools()
    )

    names = {
        tool.name
        for tool in tools_list
    }

    assert "scan_repository" in names
    assert "get_incidents" in names
    assert "inspect_incident" in names