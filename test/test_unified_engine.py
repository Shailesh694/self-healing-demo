"""Integration tests for the unified engine (mocked Gemini, real Git, real sandbox)."""
import asyncio
import hashlib
import hmac
import json
import os
import stat
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from selfheal.candidates import CandidateStore
from selfheal.engine import EngineConfig, RemediationEngine, execute_candidate
from selfheal.diagnostics import DiagnosticResult
from selfheal.policy import RepairPolicy
from selfheal.workflow import process_ci_failure
from src.selfheal.server import app

BUG = "value = 1 + '2'\nprint(value)\n"
FIXED_LINE = "value = 1 + 2"
TESTS = (
    "import subprocess, sys\n\n"
    "def test_app_runs():\n"
    "    assert subprocess.run([sys.executable, 'app.py']).returncode == 0\n"
)
GOOD_PATCH = (
    "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
    "@@ -1,2 +1,2 @@\n-value = 1 + '2'\n+value = 1 + 2\n print(value)\n"
)
LOGS = 'File "app.py", line 1\nTypeError: unsupported operand type(s) for +'


def git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app.py").write_text(BUG)
    (tmp_path / "test_app.py").write_text(TESTS)
    git(tmp_path, "init", "-q"); git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t"); git(tmp_path, "add", "."); git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def fake_ai(patches, log=None):
    """Mocked Surveyor/Coder/Reviewer pipeline: returns the given patches in order."""
    queue = list(patches)

    def prepare(**kwargs):
        if log is not None:
            log.append(kwargs["incident"])
        patch = queue.pop(0) if len(queue) > 1 else queue[0]
        return {"success": True, "patch": patch, "confidence": 0.85,
                "review": SimpleNamespace(response=SimpleNamespace(approved=True, risk_level="low")),
                "verification": {"valid": True}}
    return prepare


def run(repo, ai, *, git_commit=True, policy=True, execute=True):
    store = CandidateStore()
    out = process_ci_failure(
        {"success": False, "logs": LOGS, "git_commit": git_commit, "execute": execute},
        incident_id="inc-1", project_path=str(repo),
        policy=RepairPolicy(allow_auto_apply=policy), ai_prepare=ai, store=store,
    )
    return out, store


def head(repo):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()


def branch(repo):
    return subprocess.run(["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True).stdout.strip()


# ---- TEST A: full flow
def test_A_full_flow_ai_to_git_commit(repo):
    out, store = run(repo, fake_ai([GOOD_PATCH]))
    assert out["status"] == "repaired", out
    assert out["patch_source"] == "ai_surveyor_coder_reviewer"
    cand = store.get(out["candidate_id"])
    assert (cand.validation_ok, cand.policy_allowed, cand.sandbox_passed, cand.regression_passed) == (True,) * 4
    assert cand.risk["files_changed"] == 1 and cand.risk["lines_changed"] == 2  # from the real diff
    assert FIXED_LINE in (repo / "app.py").read_text()
    assert branch(repo).startswith("selfheal/fix-")
    assert out["repair"]["git"]["committed"] is True
    assert subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo,
                          capture_output=True, text=True).stdout.strip() == ""


# ---- TEST B: sandbox failure leaves the repository untouched
def test_B_sandbox_failure_does_not_touch_repository(repo):
    bad = GOOD_PATCH.replace("value = 1 + 2", "value = 1 + 'x'")  # still broken -> tests fail in sandbox
    before, h = (repo / "app.py").read_bytes(), head(repo)
    out, _ = run(repo, fake_ai([bad]))
    assert out["status"] in {"exhausted", "review"}
    assert any(a["stage"] == "sandbox" for a in out["repair"]["attempts"])
    assert (repo / "app.py").read_bytes() == before
    assert head(repo) == h and branch(repo) in {"master", "main"}


# ---- TEST C: failed candidate -> retry with feedback -> success
def test_C_regression_or_sandbox_failure_triggers_retry(repo):
    bad = GOOD_PATCH.replace("value = 1 + 2", "value = 1 + 'x'")
    seen = []
    out, _ = run(repo, fake_ai([bad, GOOD_PATCH], seen))
    assert out["status"] == "repaired", out
    attempts = out["repair"]["attempts"]
    assert [a["passed"] for a in attempts] == [False, True]
    assert "previous rejected attempt" in seen[1] and "sandbox" in seen[1]


# ---- TEST D: bounded retries -> exhausted, nothing changed
def test_D_three_failures_exhaust_and_rollback_decision(repo):
    bad = [GOOD_PATCH.replace("value = 1 + 2", f"value = 1 + '{i}'") for i in range(5)]
    calls = []
    out, _ = run(repo, fake_ai(bad, calls))
    assert out["status"] == "exhausted"
    assert len(calls) == 3  # default bound
    rb = out["repair"]["rollback"]
    assert rb["required"] is True and rb["repository_modified"] is False
    assert FIXED_LINE not in (repo / "app.py").read_text()


# ---- TEST E: git commit failure is NOT reported as success and is rolled back
def test_E_commit_failure_rolls_back(repo):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    h = head(repo)
    out, _ = run(repo, fake_ai([GOOD_PATCH]))
    assert out["status"] == "rolled_back", out
    assert "commit" in out["repair"]["error"]
    assert out["repair"]["rollback"]["errors"] == [] and out["repair"]["rollback"]["git_clean"] is True
    assert (repo / "app.py").read_text() == BUG and head(repo) == h
    assert branch(repo) in {"master", "main"}
    assert "selfheal/fix" not in subprocess.run(["git", "branch"], cwd=repo, capture_output=True, text=True).stdout


def test_E2_branch_creation_failure_stops_transaction(repo):
    out, store = run(repo, fake_ai([GOOD_PATCH]), execute=False)
    cand = store.get(out["candidate_id"])
    git(repo, "branch", f"selfheal/fix-{cand.candidate_id[:8]}")  # name collision
    result = execute_candidate(cand.candidate_id, store=store)
    assert result["status"] == "failed" and "branch" in result["error"]
    assert result["executed"] is False and (repo / "app.py").read_text() == BUG


# ---- TEST F: policy rejects high risk / disabled policy -> nothing executed
def test_F_policy_rejection_blocks_execution(repo):
    n = 220
    big = ("diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
           f"@@ -1,2 +1,{n + 1} @@\n-value = 1 + '2'\n"
           + "".join(f"+x{i} = {i}\n" for i in range(n)) + " print(value)\n")
    out, store = run(repo, fake_ai([big]))
    assert out["status"] == "review" and "policy" in out["repair"]["attempts"][0]["stage"]
    assert (repo / "app.py").read_text() == BUG
    cand = store.get(out["candidate_id"])
    assert cand.status == "needs_review"
    assert execute_candidate(cand.candidate_id, store=store)["executed"] is False


def test_F2_disabled_policy_never_generates(repo):
    calls = []
    out, _ = run(repo, fake_ai([GOOD_PATCH], calls), policy=False)
    assert out["status"] == "diagnosed" and calls == [] and (repo / "app.py").read_text() == BUG


# ---- execution boundary cannot be tricked
def test_execution_boundary_rechecks_state(repo):
    out, store = run(repo, fake_ai([GOOD_PATCH]), execute=False)
    assert out["status"] == "approved"
    cand = store.get(out["candidate_id"])
    cand.patch = cand.patch.replace("1 + 2", "9 + 9")                 # tampered patch
    assert "modified after approval" in execute_candidate(cand.candidate_id, store=store)["error"]
    cand.patch = cand.patch.replace("9 + 9", "1 + 2")
    (repo / "app.py").write_text(BUG + "# edited\n")                   # stale target
    git(repo, "commit", "-qam", "user change")
    assert "stale" in execute_candidate(cand.candidate_id, store=store)["error"]
    assert execute_candidate("nope", store=store)["error"] == "Unknown candidate_id"


def test_execution_boundary_requires_all_gates(repo):
    out, store = run(repo, fake_ai([GOOD_PATCH]), execute=False)
    cand = store.get(out["candidate_id"])
    cand.sandbox_passed = False
    assert "gate not passed: sandbox_passed" in execute_candidate(cand.candidate_id, store=store)["error"]


def test_staged_approval_then_execute(repo):
    out, store = run(repo, fake_ai([GOOD_PATCH]), execute=False)
    result = execute_candidate(out["candidate_id"], store=store)
    assert result["success"] is True and FIXED_LINE in (repo / "app.py").read_text()
    assert execute_candidate(out["candidate_id"], store=store)["executed"] is False  # not twice


def test_rule_based_fallback_when_ai_rejects(tmp_path):
    (tmp_path / "app.py").write_text("import os\nprint(1)\n")
    (tmp_path / "test_app.py").write_text(TESTS)
    reject = lambda **kw: {"success": False, "error": "model unavailable"}
    out = process_ci_failure(
        {"success": False, "logs": "app.py:1:1: F401 'os' imported but unused"},
        incident_id="fb", project_path=str(tmp_path),
        policy=RepairPolicy(allow_auto_apply=True), ai_prepare=reject, store=CandidateStore(),
    )
    assert out["status"] == "repaired" and out["patch_source"] == "rule_based"
    assert "import os" not in (tmp_path / "app.py").read_text()


def test_path_escape_is_rejected(repo):
    store = CandidateStore()
    diag = DiagnosticResult(error_type="X", message="m", file_path="../../etc/passwd", line_number=1)
    out = RemediationEngine(project_path=str(repo), policy=RepairPolicy(allow_auto_apply=True),
                            store=store).remediate(incident_id="i", diagnostic=diag)
    assert out["status"] == "review" and "invalid" in out["reason"]


# ---- TEST G: MCP drives the integrated workflow
def test_G_mcp_calls_integrated_workflow(repo, monkeypatch):
    from selfheal.mcp import tools
    monkeypatch.setenv("SELFHEAL_ALLOWED_ROOTS", str(repo))
    monkeypatch.delenv("SELFHEAL_MCP_ALLOW_APPLY", raising=False)
    # read-only: diagnosis only, nothing mutated, no apply permission needed
    ro = tools.run_integrated_remediation(logs=LOGS, project_path=str(repo))
    assert ro["status"] == "diagnosed" and (repo / "app.py").read_text() == BUG
    # mutation is refused unless explicitly enabled on the server side
    denied = tools.run_integrated_remediation(logs=LOGS, project_path=str(repo), auto_apply=True)
    assert denied["status"] == "error"
    assert tools.execute_approved_repair_candidate(candidate_id="x")["executed"] is False
    # outside allowed roots
    with pytest.raises(ValueError):
        tools.run_integrated_remediation(logs=LOGS, project_path="/")


def test_G2_mcp_tool_registered_and_runnable():
    from selfheal.mcp.server import create_mcp_server
    names = [t.name for t in asyncio.run(create_mcp_server().list_tools())]
    assert "run_integrated_remediation" in names and "execute_repair_candidate" not in names
    assert len(names) == len(set(names))


def test_G3_mcp_path_guard_blocks_outside_root(monkeypatch, tmp_path):
    from selfheal.mcp.server import _guarded
    monkeypatch.setenv("SELFHEAL_ALLOWED_ROOTS", str(tmp_path))
    f = _guarded(lambda repository_path: "ok")
    assert f(repository_path=str(tmp_path)) == "ok"
    with pytest.raises(ValueError):
        f(repository_path="/etc")


# ---- TEST H: webhook signature
def test_H_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("SELFHEAL_WEBHOOK_SECRET", "k")
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    body = json.dumps({"success": False, "logs": "boom"}).encode()
    good = "sha256=" + hmac.new(b"k", body, hashlib.sha256).hexdigest()
    c = TestClient(app)
    h = {"Content-Type": "application/json"}
    assert c.post("/webhook", content=body, headers={**h, "X-Hub-Signature-256": "sha256=00"}).status_code == 401
    assert c.post("/webhook", content=body, headers=h).status_code == 401
    assert c.post("/webhook", content=body, headers={**h, "X-Hub-Signature-256": good}).status_code == 200


def test_webhook_end_to_end_with_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("SELFHEAL_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.delenv("SELFHEAL_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("SELFHEAL_WEBHOOK_TOKEN", raising=False)
    (tmp_path / "main.py").write_text("import os\nprint(1)\n")
    (tmp_path / "test_main.py").write_text(
        "import subprocess, sys\n\ndef test_runs():\n"
        "    assert subprocess.run([sys.executable, 'main.py']).returncode == 0\n")
    git(tmp_path, "init", "-q"); git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t"); git(tmp_path, "add", "."); git(tmp_path, "commit", "-qm", "i")
    r = TestClient(app).post("/webhook", json={
        "success": False, "logs": "main.py:1:1: F401 'os' imported but unused",
        "auto_heal": True, "git_commit": True, "project_path": str(tmp_path)})
    wf = r.json()["workflow"]
    assert wf["status"] == "repaired", wf
    assert "import os" not in (tmp_path / "main.py").read_text()
    assert branch(tmp_path).startswith("selfheal/fix-")


# ---- transient vs permanent candidate-generation failures
def seq_ai(results, calls):
    queue = list(results)

    def prepare(**kw):
        calls.append(kw["incident"])
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, str):
            return {"success": False, "error": item}
        return item
    return prepare


def good():
    return {"success": True, "patch": GOOD_PATCH, "confidence": 0.85,
            "review": SimpleNamespace(response=SimpleNamespace(approved=True, risk_level="low")),
            "verification": {"valid": True}}


ERR_503 = "503 UNAVAILABLE. The model is overloaded. Please try again later."
ERR_429 = "429 RESOURCE_EXHAUSTED. You exceeded your current quota"


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setenv("SELFHEAL_RETRY_BACKOFF", "0")


def test_transient_503_is_retried_then_succeeds(repo):
    calls = []
    out, _ = run(repo, seq_ai([ERR_503, good()], calls))
    assert out["status"] == "repaired", out
    assert len(calls) == 2 and "candidate generation" in calls[1]
    stages = [a["stage"] for a in out["repair"]["attempts"]]
    assert stages[0] == "candidate_generation" and stages[-1] == "approved"


def test_persistent_503_uses_full_bounded_policy_and_touches_nothing(repo):
    calls = []
    out, _ = run(repo, seq_ai([ERR_503], calls))
    assert len(calls) == 3  # same bound as every other failure stage
    assert out["status"] == "exhausted" and "generation failed" in out["reason"]
    assert (repo / "app.py").read_text() == BUG


def test_generation_retries_are_configurable_but_never_exceed_max_attempts(repo, monkeypatch):
    monkeypatch.setenv("SELFHEAL_GENERATION_RETRIES", "1")
    calls = []
    run(repo, seq_ai([ERR_503], calls))
    assert len(calls) == 2
    monkeypatch.setenv("SELFHEAL_GENERATION_RETRIES", "9")
    calls.clear()
    out, _ = run(repo, seq_ai([ERR_503], calls))
    assert len(calls) == 3 and out["status"] == "exhausted"


def test_quota_exhaustion_is_not_retried(repo):
    calls = []
    out, _ = run(repo, seq_ai([ERR_429], calls))
    assert len(calls) == 1 and out["status"] == "review"
    assert (repo / "app.py").read_text() == BUG


def test_quota_message_mentioning_503_is_still_not_retried():
    from selfheal.engine import is_transient_ai_failure
    assert is_transient_ai_failure(ERR_503) is True
    assert is_transient_ai_failure(ERR_429) is False
    assert is_transient_ai_failure("429 RESOURCE_EXHAUSTED ... 503") is False
    assert is_transient_ai_failure("model returned no patch") is False


def test_no_supported_fix_is_not_retried(repo):
    calls = []
    out, _ = run(repo, seq_ai(["Coder produced no patch"], calls))
    assert len(calls) == 1 and out["status"] == "review"


def test_ai_503_still_uses_rule_based_fallback_without_retrying(tmp_path):
    (tmp_path / "main.py").write_text("import os\nprint(1)\n")
    (tmp_path / "test_main.py").write_text(TESTS.replace("app.py", "main.py"))
    calls = []
    out = process_ci_failure(
        {"success": False, "logs": "main.py:1:1: F401 'os' imported but unused"},
        incident_id="fb", project_path=str(tmp_path),
        policy=RepairPolicy(allow_auto_apply=True),
        ai_prepare=seq_ai([ERR_503], calls), store=CandidateStore(),
    )
    assert out["status"] == "repaired" and out["patch_source"] == "rule_based"
    assert len(calls) == 1  # deterministic fallback used instead of re-calling a failing AI
