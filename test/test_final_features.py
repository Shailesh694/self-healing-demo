import asyncio
import hashlib
import hmac
import importlib
import json
import subprocess
import sys

from fastapi.testclient import TestClient

from selfheal.analysis.repair_strategy import generate_repair_patch
from selfheal.ci import normalize_github_payload
from selfheal.diagnostics import diagnose
from selfheal.gate import check_rewrite
from selfheal.mcp.http import create_secured_http_app
from selfheal.repository.index import RepositoryIndex
from src.selfheal.server import app

ANSI_LOG = "\x1b[1mmain.py\x1b[m\x1b[36m:\x1b[m1\x1b[36m:\x1b[m1\x1b[36m:\x1b[m \x1b[1m\x1b[31mF401\x1b[m 'os' imported but unused\r\n"


def _git(p, *a):
    subprocess.run(["git", *a], cwd=p, check=True, capture_output=True)


def _repo(p, body):
    (p / "main.py").write_text(body)
    (p / "test_main.py").write_text(
        "import subprocess, sys\n"
        "def test_runs():\n"
        "    assert subprocess.run([sys.executable, 'main.py']).returncode == 0\n")
    _git(p, "init", "-q"); _git(p, "config", "user.email", "t@t"); _git(p, "config", "user.name", "t")
    _git(p, "add", "."); _git(p, "commit", "-qm", "i")


# ---- diagnostics / strategies
def test_diagnose_flake8_with_ansi():
    d = diagnose(ANSI_LOG)
    assert (d.error_type, d.file_path, d.line_number) == ("F401", "main.py", 1)
    assert "imported but unused" in d.message


def test_unused_import_patch_and_safety(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("import os\nprint(1)\n")
    assert "-import os" in generate_repair_patch(file_path=str(f), error_type="F401",
                                                  message="F401 'os' imported but unused", line_number=1)
    f.write_text("import os\nprint(os.getcwd())\n")  # actually used -> refuse
    assert generate_repair_patch(file_path=str(f), error_type="F401",
                                 message="F401 'os' imported but unused", line_number=1) is None
    f.write_text("import os, sys\n")  # multi-name -> refuse
    assert generate_repair_patch(file_path=str(f), error_type="F401",
                                 message="F401 'os' imported but unused", line_number=1) is None


def test_trailing_whitespace_patch(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1   \n")
    p = generate_repair_patch(file_path=str(f), error_type="W291", message="W291", line_number=1)
    assert "+x = 1\n" in p


def test_e2e_flake8_log_fixed_and_committed(tmp_path, monkeypatch):
    monkeypatch.setenv("SELFHEAL_ALLOWED_ROOTS", str(tmp_path))
    _repo(tmp_path, "import os\nprint(1)\n")
    r = TestClient(app).post("/webhook", json={
        "success": False, "logs": ANSI_LOG, "auto_heal": True,
        "git_commit": True, "project_path": str(tmp_path)})
    wf = r.json()["workflow"]
    assert wf["status"] == "repaired", wf
    assert wf["repair"]["git"]["committed"] is True
    assert "import os" not in (tmp_path / "main.py").read_text()


# ---- github + signatures
def test_normalize_github_payload():
    out = normalize_github_payload({"workflow_run": {"conclusion": "failure", "head_branch": "m",
                                                      "head_sha": "abc", "id": 7, "name": "CI"}})
    assert out["success"] is False and out["incident_id"] == "gh-7" and out["branch"] == "m"


def test_github_signature_auth(monkeypatch):
    monkeypatch.setenv("SELFHEAL_WEBHOOK_SECRET", "s3")
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    body = json.dumps({"workflow_run": {"conclusion": "success", "id": 1}}).encode()
    sig = "sha256=" + hmac.new(b"s3", body, hashlib.sha256).hexdigest()
    c = TestClient(app)
    h = {"Content-Type": "application/json", "X-GitHub-Event": "workflow_run"}
    assert c.post("/webhook", content=body, headers=h).status_code == 401
    assert c.post("/webhook", content=body, headers={**h, "X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    ok = c.post("/webhook", content=body, headers={**h, "X-Hub-Signature-256": sig})
    assert ok.status_code == 200 and ok.json()["workflow"]["status"] == "ignored"


def test_invalid_json_is_400(monkeypatch):
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    monkeypatch.delenv("SELFHEAL_WEBHOOK_SECRET", raising=False)
    assert TestClient(app).post("/webhook", content=b"{nope",
                                headers={"Content-Type": "application/json"}).status_code == 400


# ---- MCP http auth
def test_mcp_http_requires_token(monkeypatch):
    monkeypatch.delenv("SELFHEAL_MCP_TOKEN", raising=False)
    try:
        create_secured_http_app()
        assert False, "should require a token"
    except RuntimeError:
        pass
    c = TestClient(create_secured_http_app("tok"), raise_server_exceptions=False)
    assert c.post("/mcp").status_code == 401
    assert c.post("/mcp", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.post("/mcp", headers={"Authorization": "Bearer tok"}).status_code != 401


def test_diagnose_incident_tool_registered():
    from selfheal.mcp.server import create_mcp_server
    names = [t.name for t in asyncio.run(create_mcp_server().list_tools())]
    assert "diagnose_incident" in names


# ---- scale + gate
def test_index_scales_and_limits(tmp_path):
    for i in range(1500):
        d = tmp_path / f"pkg{i % 30}"
        d.mkdir(exist_ok=True)
        (d / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.py").write_text("x=1\n")
    (tmp_path / "bad.py").write_text("def (:\n")
    idx = RepositoryIndex(tmp_path).build()
    assert len(idx.files) >= 1500
    assert not any("node_modules" in f for f in idx.files)
    capped = RepositoryIndex(tmp_path, max_files=100).build()
    assert capped.truncated and len(capped.files) == 100


def test_gate_multi_format():
    assert check_rewrite("c.json", "{}", '{"a": 1}').ok
    assert not check_rewrite("c.json", "{}", "{bad").ok
    assert check_rewrite("p.toml", "", "a = 1\n").ok
    assert not check_rewrite("p.toml", "", "a = = 1\n").ok
    assert check_rewrite("w.yml", "", "a: 1\n").ok
    assert not check_rewrite("app.rb", "", "puts 1").ok  # unsupported -> fail closed


def test_heal_is_a_thin_wrapper_and_imports_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.syspath_prepend(".")
    sys.modules.pop("heal", None)
    heal = importlib.import_module("heal")
    assert callable(heal.main)
    src = open("heal.py", encoding="utf-8").read()
    assert "genai" not in src and "selfheal.ci_runner" in src  # no separate healing implementation


# ---- deterministic style strategies (flake8 E231 / E225 / E302 / E305)
def _fix(tmp_path, source, code, msg, line, col):
    f = tmp_path / "a.py"
    f.write_text(source)
    patch = generate_repair_patch(file_path=str(f), error_type=code, message=msg, line_number=line, column=col)
    assert patch is not None
    from selfheal.analysis.executor import apply_patch
    apply_patch(file_path=str(f), patch=patch, dry_run=False)
    return f.read_text()


def test_e231_adds_space_after_comma(tmp_path):
    assert _fix(tmp_path, "def f(a,b):\n    return a\n", "E231", "E231 missing whitespace after ','", 1, 8) \
        == "def f(a, b):\n    return a\n"


def test_e231_refuses_when_column_is_not_a_separator(tmp_path):
    f = tmp_path / "a.py"; f.write_text("x = (1,2)\n")
    assert generate_repair_patch(file_path=str(f), error_type="E231", message="m", line_number=1, column=2) is None


def test_e225_spaces_around_operator(tmp_path):
    assert _fix(tmp_path, "def f():\n    result=1+2\n    return result\n", "E225",
                "E225 missing whitespace around operator", 2, 11) == "def f():\n    result = 1+2\n    return result\n"


def test_e302_and_e305_insert_missing_blank_lines(tmp_path):
    out = _fix(tmp_path, "import os\n\ndef f():\n    return 1\n", "E302", "E302 expected 2 blank lines, found 1", 3, 1)
    assert out == "import os\n\n\ndef f():\n    return 1\n"
    out = _fix(tmp_path, "def f():\n    return 1\n\nprint(f())\n", "E305",
               "E305 expected 2 blank lines after class or function definition, found 1", 4, 1)
    assert out == "def f():\n    return 1\n\n\nprint(f())\n"


def test_style_strategies_never_break_syntax(tmp_path):
    f = tmp_path / "a.py"; f.write_text("def f(:\n    x=1\n")  # already invalid: refuse
    assert generate_repair_patch(file_path=str(f), error_type="E225", message="m", line_number=2, column=6) is None


def test_ci_runner_orders_findings_bottom_up_and_right_to_left():
    from selfheal.ci_runner import parse_linter_issues
    log = ("main.py:4:1: E302 expected 2 blank lines, found 1\nmain.py:4:20: E231 missing whitespace after ','\n"
           "main.py:2:1: F401 'sys' imported but unused\n")
    assert [(d.line_number, d.column) for d in parse_linter_issues(log)] == [(4, 20), (4, 1), (2, 1)]
