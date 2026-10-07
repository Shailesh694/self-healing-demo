from fastapi.testclient import TestClient

from selfheal.mcp.server import create_mcp_server
from selfheal.runtime import incident_manager as mcp_side_manager
from src.selfheal.runtime import incident_manager as api_side_manager
from src.selfheal.server import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_webhook_creates_incident_and_diagnoses():
    before = len(api_side_manager.list_open())
    r = client.post("/webhook", json={
        "incident_id": "e2e-1",
        "success": False,
        "logs": "File \"app.py\", line 3\nNameError: name 'x' is not defined",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["workflow"]["status"] == "diagnosed"
    assert body["workflow"]["diagnostic"]["error_type"] == "NameError"
    assert len(api_side_manager.list_open()) == before + 1


def test_webhook_rejects_non_dict():
    assert client.post("/webhook", json=[1]).status_code == 422


def test_shared_runtime_across_import_paths():
    assert mcp_side_manager is api_side_manager


def test_no_duplicate_mcp_tools():
    import asyncio
    tools = asyncio.run(create_mcp_server().list_tools())
    names = [t.name for t in tools]
    assert len(names) == len(set(names)) == 18
