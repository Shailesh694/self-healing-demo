"""CI path end to end with REAL flake8 output (E226-E228 enabled), plus webhook path guard."""
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from selfheal.analysis.executor import apply_patch
from selfheal.analysis.repair_strategy import generate_repair_patch
from selfheal.candidates import CandidateStore
from src.selfheal.server import app

pytest.importorskip("flake8")

SAMPLE = (
    "import os\nimport sys\n\ndef calculate_sum(a,b):\n    result=a+b\n    return result\n\n"
    "print(calculate_sum(5,10))\n"
)
TEST = (
    "import subprocess, sys\n\ndef test_prints_sum():\n"
    "    out = subprocess.run([sys.executable, 'main.py'], capture_output=True, text=True)\n"
    "    assert out.returncode == 0 and out.stdout.strip() == '15'\n"
)


def flake8(cwd, *extra):
    return subprocess.run([sys.executable, "-m", "flake8", "main.py", *extra],
                          cwd=cwd, capture_output=True, text=True).stdout


def test_ci_runner_heals_real_flake8_findings_including_e226(tmp_path, monkeypatch):
    from selfheal.ci_runner import run_ci_remediation

    (tmp_path / "main.py").write_text(SAMPLE)
    (tmp_path / "test_main.py").write_text(TEST)
    # replacing the default ignore list enables E226 (ignored by default flake8)
    log = flake8(tmp_path, "--ignore=W503,W504")
    assert {"F401", "E302", "E231", "E225", "E226", "E305"} <= {
        line.split()[1] for line in log.splitlines()}
    (tmp_path / "linter_errors.log").write_text(log)
    monkeypatch.setenv("SELFHEAL_RETRY_BACKOFF", "0")

    summary = run_ci_remediation(project_path=str(tmp_path), store=CandidateStore())

    assert summary["total"] == summary["repaired"] == len(log.splitlines()), summary
    assert flake8(tmp_path, "--ignore=W503,W504") == ""  # clean even with E226 enabled
    assert "result = a + b" in (tmp_path / "main.py").read_text()
    out = subprocess.run([sys.executable, "main.py"], cwd=tmp_path, capture_output=True, text=True)
    assert out.stdout.strip() == "15"


@pytest.mark.parametrize("code,source,col,expected", [
    ("E226", "x = 1+2\n", 6, "x = 1 + 2\n"),
    ("E226", "y = a**2\n", 6, "y = a ** 2\n"),
    ("E227", "z = a<<2\n", 6, "z = a << 2\n"),
    ("E228", "m = a%3\n", 6, "m = a % 3\n"),
])
def test_arithmetic_bitwise_modulo_spacing(tmp_path, code, source, col, expected):
    f = tmp_path / "a.py"
    f.write_text(source)
    patch = generate_repair_patch(file_path=str(f), error_type=code, message="m",
                                  line_number=1, column=col)
    assert patch is not None
    apply_patch(file_path=str(f), patch=patch, dry_run=False)
    assert f.read_text() == expected


def test_arithmetic_strategy_refuses_a_non_operator_column(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1+2\n")
    assert generate_repair_patch(file_path=str(f), error_type="E226", message="m",
                                 line_number=1, column=1) is None


# ---- webhook project_path guard
def test_webhook_rejects_project_path_outside_allowed_roots(tmp_path, monkeypatch):
    allowed, other = tmp_path / "allowed", tmp_path / "other"
    allowed.mkdir(); other.mkdir()
    monkeypatch.setenv("SELFHEAL_ALLOWED_ROOTS", str(allowed))
    monkeypatch.delenv("SELFHEAL_PROJECT_PATH", raising=False)
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    monkeypatch.delenv("SELFHEAL_WEBHOOK_SECRET", raising=False)
    c = TestClient(app)
    body = {"success": False, "logs": "boom", "auto_heal": True, "project_path": str(other)}
    r = c.post("/webhook", json=body)
    assert r.status_code == 403 and "allowed roots" in r.json()["detail"]
    assert c.post("/webhook", json={**body, "project_path": "../../etc"}).status_code == 403
    assert c.post("/webhook", json={**body, "project_path": str(allowed)}).status_code == 200


def test_server_configured_project_path_overrides_payload(tmp_path, monkeypatch):
    fixed = tmp_path / "fixed"
    fixed.mkdir()
    monkeypatch.setenv("SELFHEAL_PROJECT_PATH", str(fixed))
    monkeypatch.setenv("SELFHEAL_ALLOWED_ROOTS", str(tmp_path / "nowhere"))
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    monkeypatch.delenv("SELFHEAL_WEBHOOK_SECRET", raising=False)
    r = TestClient(app).post("/webhook", json={
        "success": False, "logs": "boom", "project_path": "/etc"})
    assert r.status_code == 200
    assert r.json()["event"]["payload"]["project_path"] == str(fixed.resolve())
