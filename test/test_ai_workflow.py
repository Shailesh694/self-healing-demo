import subprocess
from types import SimpleNamespace

from selfheal.agent_workflow import propose_ai_patch
from selfheal.workflow import process_ci_failure
from selfheal.policy import RepairPolicy


def _approved(patch):
    def prepare(**kw):
        return {"success": True, "patch": patch, "confidence": 0.8,
                "review": SimpleNamespace(response=SimpleNamespace(approved=True, risk_level="low")),
                "verification": {"valid": True}}
    return prepare


def test_reviewer_rejection_blocks(tmp_path):
    f = tmp_path / "a.py"; f.write_text("x = 1\n")
    def prep(**kw):
        return {"success": True, "patch": "p", "confidence": 0.9,
                "review": SimpleNamespace(response=SimpleNamespace(approved=False, risk_level="low"))}
    r = propose_ai_patch(incident="i", file_path=str(f), project_path=str(tmp_path), prepare=prep)
    assert not r["approved"] and "reviewer" in r["reason"]


def test_high_risk_review_blocks(tmp_path):
    f = tmp_path / "a.py"; f.write_text("x = 1\n")
    def prep(**kw):
        return {"success": True, "patch": "p", "confidence": 0.9,
                "review": SimpleNamespace(response=SimpleNamespace(approved=True, risk_level="HIGH"))}
    assert not propose_ai_patch(incident="i", file_path=str(f), project_path=str(tmp_path), prepare=prep)["approved"]


def test_deterministic_failure_blocks(tmp_path):
    f = tmp_path / "a.py"; f.write_text("x = 1\n")
    prep = lambda **kw: {"success": False, "error": "bad diff"}
    r = propose_ai_patch(incident="i", file_path=str(f), project_path=str(tmp_path), prepare=prep)
    assert not r["approved"] and r["reason"] == "bad diff"


def test_pipeline_exception_is_contained(tmp_path):
    f = tmp_path / "a.py"; f.write_text("x = 1\n")
    def boom(**kw): raise RuntimeError("no api key")
    r = propose_ai_patch(incident="i", file_path=str(f), project_path=str(tmp_path), prepare=boom)
    assert not r["approved"] and "no api key" in r["reason"]


def test_workflow_uses_ai_patch_end_to_end(tmp_path):
    # a TypeError the rule-based strategy cannot fix; AI proposes the diff.
    app = tmp_path / "app.py"
    app.write_text("value = 1 + '2'\n")
    (tmp_path / "test_app.py").write_text(
        "import subprocess, sys\n"
        "def test_runs():\n"
        "    assert subprocess.run([sys.executable, 'app.py']).returncode == 0\n")
    for c in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
              ["add", "."], ["commit", "-qm", "i"]):
        subprocess.run(["git", *c], cwd=tmp_path, check=True, capture_output=True)
    patch = ("diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
             "@@ -1 +1 @@\n-value = 1 + '2'\n+value = 1 + 2\n")
    logs = f'File "{app}", line 1\nTypeError: unsupported operand type(s)'
    out = process_ci_failure(
        {"success": False, "logs": logs, "use_agents": True, "git_commit": True},
        incident_id="ai-1", project_path=str(tmp_path),
        policy=RepairPolicy(allow_auto_apply=True), ai_prepare=_approved(patch))
    assert out.get("patch_source") == "ai_surveyor_coder_reviewer", out
    print(out.get("repair"))
    assert out["status"] == "repaired", out.get("repair")
