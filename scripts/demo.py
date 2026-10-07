"""
End-to-end demo of the SelfHeal engine on a real Python bug.

  python scripts/demo.py                    # rule-based fix (no AI needed)
  python scripts/demo.py --mode ai-scripted # AI path with a SCRIPTED stand-in for Gemini
  python scripts/demo.py --mode ai-live     # real Gemini (needs GEMINI_API_KEY + quota)

The scripted mode is NOT Gemini: it feeds a fixed patch through the real
Surveyor-output handling and every deterministic gate, to demonstrate the
architecture when no API quota is available. ai-live uses the real model.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from selfheal.candidates import CandidateStore  # noqa: E402
from selfheal.policy import RepairPolicy  # noqa: E402
from selfheal.workflow import process_ci_failure  # noqa: E402

SCENARIOS = {
    "nameerror": ("print(foo)\n", None),
    "typeerror": (
        "value = 1 + '2'\nprint(value)\n",
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n"
        "-value = 1 + '2'\n+value = 1 + 2\n print(value)\n",
    ),
}
TEST = ("import subprocess, sys\n\ndef test_app_runs():\n"
        "    assert subprocess.run([sys.executable, 'app.py']).returncode == 0\n")


def sh(*cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def scripted_ai(patch):
    def prepare(**_):
        return {"success": True, "patch": patch, "confidence": 0.85, "verification": {"valid": True},
                "review": SimpleNamespace(response=SimpleNamespace(approved=True, risk_level="low"))}
    return prepare


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["rule", "ai-scripted", "ai-live"], default="rule")
    ap.add_argument("--bug", choices=list(SCENARIOS), default=None)
    args = ap.parse_args()
    bug = args.bug or ("nameerror" if args.mode == "rule" else "typeerror")
    source, scripted_patch = SCENARIOS[bug]

    repo = Path(tempfile.mkdtemp(prefix="selfheal-demo-"))
    (repo / "app.py").write_text(source)
    (repo / "test_app.py").write_text(TEST)
    for c in (["init", "-q"], ["config", "user.email", "demo@example.com"],
              ["config", "user.name", "demo"], ["add", "."], ["commit", "-qm", "broken app"]):
        sh("git", *c, cwd=repo)

    print(f"1. Broken project created in {repo}")
    ci = sh(sys.executable, "app.py", cwd=repo)
    print(f"2. CI failure (exit {ci.returncode}):\n   " + ci.stderr.strip().splitlines()[-1])

    ai = None
    if args.mode == "ai-scripted":
        if scripted_patch is None:
            print("   (scripted mode needs --bug typeerror)"); return 2
        ai = scripted_ai(scripted_patch)
        print("3. AI path: SCRIPTED stand-in for Surveyor/Coder/Reviewer (not Gemini)")
    elif args.mode == "ai-live":
        os.environ["SELFHEAL_GEMINI_ENABLED"] = "true"
        print("3. AI path: live Gemini Surveyor -> Coder -> Reviewer")
    else:
        print("3. Rule-based deterministic strategy (AI not required)")

    result = process_ci_failure(
        {"success": False, "logs": ci.stderr, "git_commit": True, "project_path": str(repo)},
        incident_id="demo-1", project_path=str(repo),
        policy=RepairPolicy(allow_auto_apply=True), ai_prepare=ai, store=CandidateStore(),
        )
    d = result["diagnostic"]
    print(f"4. Diagnosis: {d.error_type} at {Path(d.file_path or '').name}:{d.line_number}")
    for a in result.get("repair", {}).get("attempts", []):
        print(f"5. Attempt {a['attempt']}: source={a.get('source')} stage={a['stage']} -> {a['reason'][:80]}")
    cand = result.get("repair", {}).get("candidate") or {}
    if cand:
        print(f"   Risk (from real diff): {cand['risk']}  gates: validation={cand['validation_ok']} "
              f"policy={cand['policy_allowed']} sandbox={cand['sandbox_passed']} regression={cand['regression_passed']}")
    print(f"6. RESULT: {result['status'].upper()}  {result.get('reason', '')}")
    print("7. Git:", sh("git", "log", "--oneline", cwd=repo).stdout.strip().replace("\n", " | "),
          "| branch:", sh("git", "branch", "--show-current", cwd=repo).stdout.strip())
    print("8. app.py now:\n   " + (repo / "app.py").read_text().strip().replace("\n", "\n   "))
    final = sh(sys.executable, "-m", "pytest", "-q", cwd=repo)
    print("9. Tests after repair:", final.stdout.strip().splitlines()[-1])
    return 0 if result["status"] == "repaired" else 1


if __name__ == "__main__":
    sys.exit(main())
