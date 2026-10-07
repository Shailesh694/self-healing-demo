import subprocess

from fastapi.testclient import TestClient

from selfheal.analysis.repair import repair_and_verify
from selfheal.incident_manager import IncidentManager
from selfheal.models import Incident
from src.selfheal.server import app


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _make_repo(tmp_path, body, test_body):
    (tmp_path / "app.py").write_text(body)
    (tmp_path / "test_app.py").write_text(test_body)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")


def test_incident_manager_persists_across_instances(tmp_path):
    f = tmp_path / "state.json"
    a = IncidentManager(f)
    rec = a.create(Incident(source="s", code="c", message="m", file_path="x.py", line=2))
    b = IncidentManager(f)  # simulates a second process
    assert len(b.list_open()) == 1
    b.close(b.list_open()[0])
    assert a.list_open() == []
    assert rec.incident.file_path == "x.py"


def test_webhook_token_required_when_configured(monkeypatch):
    monkeypatch.setenv("SELFHEAL_WEBHOOK_TOKEN", "secret")
    c = TestClient(app)
    body = {"success": False, "logs": "boom"}
    assert c.post("/webhook", json=body).status_code == 401
    assert c.post("/webhook", json=body, headers={"X-Selfheal-Token": "bad"}).status_code == 401
    assert c.post("/webhook", json=body, headers={"X-Selfheal-Token": "secret"}).status_code == 200


def test_webhook_generates_incident_id_when_missing(monkeypatch):
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    r = TestClient(app).post("/webhook", json={"success": False, "logs": "boom"})
    assert r.json()["event"]["payload"]["incident_id"] != "unknown"


def test_git_commit_requires_repository(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("print(1)\n")
    r = repair_and_verify(file_path=str(f), problem="p", confidence=0.9,
                          patch="x", project_path=str(tmp_path), git_commit=True)
    assert r["status"] == "review"


def test_git_commit_refuses_dirty_tree(tmp_path):
    _make_repo(tmp_path, "print(1)\n", "def test_ok():\n    assert True\n")
    (tmp_path / "app.py").write_text("print(2)\n")
    r = repair_and_verify(file_path=str(tmp_path / "app.py"), problem="p",
                          confidence=0.9, patch="x", project_path=str(tmp_path),
                          git_commit=True)
    assert r["status"] == "review"
    assert "uncommitted" in r["reason"]


def test_e2e_webhook_fix_commits_on_branch(tmp_path, monkeypatch):
    monkeypatch.setenv("SELFHEAL_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    _make_repo(
        tmp_path,
        "print(foo)\n",
        "import subprocess, sys\n\n"
        "def test_runs():\n"
        "    r = subprocess.run([sys.executable, 'app.py'], capture_output=True)\n"
        "    assert r.returncode == 0\n",
    )
    app_file = tmp_path / "app.py"
    logs = f'File "{app_file}", line 1\nNameError: name \'foo\' is not defined'
    r = TestClient(app).post("/webhook", json={
        "success": False, "logs": logs, "auto_heal": True,
        "git_commit": True, "project_path": str(tmp_path),
    })
    assert r.status_code == 200
    wf = r.json()["workflow"]
    print(wf)
    assert wf["status"] == "repaired", wf
    assert wf["repair"]["git"]["committed"] is True
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=tmp_path,
                            capture_output=True, text=True).stdout.strip()
    assert branch.startswith("selfheal/fix-")
