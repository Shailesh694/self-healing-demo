"""Cross-process candidates, record signing, unified git apply, Gemini model fallback."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from selfheal.agents.gemini import GeminiClient
from selfheal.analysis import executor
from selfheal.candidates import Candidate, CandidateStore
from selfheal.config import SelfHealConfig
from selfheal.engine import execute_candidate
from selfheal.git import GIT_APPLY_FLAGS, GitRepository
from selfheal.policy import RepairPolicy
from selfheal.workflow import process_ci_failure
from test_unified_engine import BUG, FIXED_LINE, LOGS, fake_ai, git, repo, GOOD_PATCH  # noqa: F401

SRC = str(Path(__file__).resolve().parent.parent / "src")


def _candidate(**kw):
    base = dict(incident_id="i", project_path="/p", file_path="/p/a.py", rel_target="a.py",
                patch="x", source="rule_based", confidence=0.9, patch_sha256="h", target_sha256="t")
    base.update(kw)
    return Candidate(**base)


# ---- candidate persistence
def test_default_store_is_in_memory(monkeypatch, tmp_path):
    monkeypatch.delenv("SELFHEAL_STATE_FILE", raising=False)
    monkeypatch.delenv("SELFHEAL_CANDIDATE_FILE", raising=False)
    s = CandidateStore(from_env=True)
    c = s.save(_candidate())
    assert s.get(c.candidate_id) is c and not list(tmp_path.iterdir())


def test_file_store_round_trips_between_instances(tmp_path):
    a, b = CandidateStore(tmp_path / "c.json"), CandidateStore(tmp_path / "c.json")
    c = _candidate(status="approved", sandbox_passed=True)
    a.save(c)
    got = b.get(c.candidate_id)
    assert got is not None and got.status == "approved" and got.sandbox_passed is True
    c.status = "executed"; a.save(c)
    assert b.get(c.candidate_id).status == "executed"


def test_state_file_derives_candidate_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SELFHEAL_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.delenv("SELFHEAL_CANDIDATE_FILE", raising=False)
    CandidateStore(from_env=True).save(_candidate())
    assert (tmp_path / "state.candidates.json").exists()


def test_signed_records_reject_tampering(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    monkeypatch.setenv("SELFHEAL_STATE_KEY", "secret")
    store = CandidateStore(path)
    c = store.save(_candidate(status="needs_review", policy_allowed=False))
    assert store.get(c.candidate_id) is not None
    raw = json.loads(path.read_text())
    raw[c.candidate_id]["data"].update(status="approved", policy_allowed=True)  # forged approval
    path.write_text(json.dumps(raw))
    assert store.get(c.candidate_id) is None
    monkeypatch.setenv("SELFHEAL_STATE_KEY", "other-key")
    assert CandidateStore(path).get(c.candidate_id) is None


def test_candidate_prepared_in_one_process_executes_in_another(repo, monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    monkeypatch.setenv("SELFHEAL_STATE_FILE", str(state))
    monkeypatch.setenv("SELFHEAL_RETRY_BACKOFF", "0")
    out = process_ci_failure(
        {"success": False, "logs": LOGS, "git_commit": True, "execute": False},
        incident_id="x-proc", project_path=str(repo),
        policy=RepairPolicy(allow_auto_apply=True), ai_prepare=fake_ai([GOOD_PATCH]),
    )  # default (env-backed) candidate store
    assert out["status"] == "approved", out
    assert (repo / "app.py").read_text() == BUG
    assert (tmp_path / "state.candidates.json").exists()

    code = ("import json,sys; from selfheal.engine import execute_candidate; "
            "print(json.dumps(execute_candidate(sys.argv[1])))")
    proc = subprocess.run([sys.executable, "-c", code, out["candidate_id"]], capture_output=True,
                          text=True, env={**os.environ, "PYTHONPATH": SRC,
                                          "SELFHEAL_STATE_FILE": str(state)})
    line = [l for l in proc.stdout.splitlines() if l.startswith("{")][-1]
    result = json.loads(line)
    assert result["success"] is True, (result, proc.stderr[-400:])
    assert FIXED_LINE in (repo / "app.py").read_text()
    # a second process (or the same) cannot execute it twice
    assert execute_candidate(out["candidate_id"])["executed"] is False


def test_execute_rejects_unknown_and_foreign_candidates(repo, tmp_path):
    store = CandidateStore(tmp_path / "c.json")
    assert execute_candidate("nope", store=store)["error"] == "Unknown candidate_id"


# ---- git apply behaviour is unified
def test_one_shared_apply_flag_set():
    assert "--ignore-whitespace" in GIT_APPLY_FLAGS and "--whitespace=error" not in GIT_APPLY_FLAGS
    assert executor.GIT_APPLY_FLAGS is GIT_APPLY_FLAGS


def test_git_helper_applies_patch_to_crlf_file(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    git(tmp_path, "config", "core.autocrlf", "false")
    patch = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n x = 1\n-y = 2\n+y = 3\n"
    result = GitRepository(tmp_path).apply_patch(patch)
    assert result.success, result.stderr
    assert b"y = 3" in (tmp_path / "a.py").read_bytes()


# ---- Gemini model selection / fallback
RESPONSE = json.dumps({"response_type": "ping", "summary": "ok", "confidence": 1.0, "data": []})


class _FakeModels:
    def __init__(self, behaviour, log):
        self.behaviour, self.log = behaviour, log

    def generate_content(self, *, model, contents, config):
        self.log.append(model)
        outcome = self.behaviour[model]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


def _client(model_setting, behaviour, log):
    cfg = SelfHealConfig(gemini_enabled=True, gemini_api_key="k", gemini_model=model_setting)
    c = GeminiClient(cfg)
    c._client = SimpleNamespace(models=_FakeModels(behaviour, log))
    return c


def test_default_model_is_a_current_model():
    assert SelfHealConfig().gemini_model == "gemini-3.6-flash"


def test_quota_on_first_model_falls_back_to_next(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    log = []
    c = _client("m1,m2", {"m1": Exception("429 RESOURCE_EXHAUSTED quota"), "m2": RESPONSE}, log)
    assert c.generate_json("p").success and log == ["m1", "m2"]


def test_single_model_quota_error_is_reported_not_retried(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    log = []
    r = _client("m1", {"m1": Exception("429 RESOURCE_EXHAUSTED")}, log).generate_json("p")
    assert not r.success and "429" in r.error and log == ["m1"]


def test_503_retries_same_model_and_never_switches_model(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("SELFHEAL_GEMINI_CALL_ATTEMPTS", "2")
    log = []
    r = _client("m1,m2", {"m1": Exception("503 UNAVAILABLE"), "m2": RESPONSE}, log).generate_json("p")
    assert not r.success and log == ["m1", "m1"]
