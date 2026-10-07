"""
RemediationEngine: the single authoritative remediation path.

    diagnosis
      -> candidate proposal (AI Surveyor/Coder/Reviewer, rule-based fallback)
      -> structural + security validation
      -> risk computed from the real diff -> policy gate
      -> sandbox (patched temp copy, tests run there)
      -> regression gate (baseline vs candidate checks + file scope)
      -> approved candidate recorded in the CandidateStore
      -> transactional execution (Git branch -> apply -> tests -> scope -> commit)
      -> rollback on any failure
    with a bounded retry loop around candidate generation.

AI may propose and review; every gate above is deterministic and
authoritative. MCP is only an interface to this module.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .agent_workflow import propose_ai_patch
from .analysis.diff import parse_diff, parse_patch
from .analysis.executor import apply_patch
from .analysis.repair_strategy import generate_repair_patch
from .analysis.scorer import assess_risk
from .analysis.tests import run_tests
from .analysis.validator import validate_candidate
from .candidates import Candidate, CandidateStore, candidate_store, sha256_text
from .gate import check_rewrite
from .git import GitRepository
from .logger import get_logger
from .policy import RepairPolicy
from .regression import CheckResult
from .regression_gate import RegressionGate
from .regression_scope import compare_file_scope
from .regression_snapshot import snapshot_files
from .retry import MAX_RETRY_ATTEMPTS, RetryAttempt, RetryController
from .rollback_controller import RollbackController
from .sandbox import COPY_IGNORE, SandboxVerifier
from .security.commands import default_test_command, validate_test_command
from .security.paths import resolve_within
from .service import SelfHealService

log = get_logger("selfheal.engine")

RULE_BASED_CONFIDENCE = 0.9  # fixed for deterministic strategies; not a model estimate
SOURCE_RULE = "rule_based"
SOURCE_AI = "ai_surveyor_coder_reviewer"


@dataclass
class EngineConfig:
    max_attempts: int = MAX_RETRY_ATTEMPTS
    sandbox_timeout: int = 60
    test_target: str = "."
    test_command: list[str] | None = None
    git_commit: bool = False
    execute: bool = True
    use_ai: bool | None = None  # None = auto (use AI when enabled), False = never
    branch_prefix: str = "selfheal/fix"
    # Extra candidate-generation attempts after a TRANSIENT AI failure (503,
    # timeout). Counted inside max_attempts. Quota (429) is never retried.
    generation_retries: int = MAX_RETRY_ATTEMPTS - 1  # full bounded policy by default
    retry_backoff: float = 2.0

    @classmethod
    def from_environment(cls, **overrides) -> "EngineConfig":
        cfg = cls(
            max_attempts=min(
                int(os.getenv("SELFHEAL_MAX_ATTEMPTS", str(MAX_RETRY_ATTEMPTS))),
                MAX_RETRY_ATTEMPTS,
            ),
            sandbox_timeout=int(os.getenv("SELFHEAL_SANDBOX_TIMEOUT", "60")),
            test_target=os.getenv("SELFHEAL_TEST_TARGET", "."),
            generation_retries=int(
                os.getenv("SELFHEAL_GENERATION_RETRIES", str(MAX_RETRY_ATTEMPTS - 1))
            ),
            retry_backoff=float(os.getenv("SELFHEAL_RETRY_BACKOFF", "2")),
        )
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg


@dataclass
class _Proposal:
    patch: str | None
    source: str | None = None
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    retryable: bool = False  # generation failed for a transient reason


@dataclass
class _Failure:
    stage: str
    reason: str
    terminal: bool = False


_QUOTA = re.compile(r"\b429\b|RESOURCE_EXHAUSTED|quota|rate.?limit", re.IGNORECASE)
_TRANSIENT = re.compile(
    r"\b(500|502|503|504)\b|UNAVAILABLE|DEADLINE_EXCEEDED|overloaded|"
    r"timed out|timeout|temporarily",
    re.IGNORECASE,
)


def is_transient_ai_failure(reason: str) -> bool:
    """Retryable provider outage. Quota exhaustion is never retried."""
    return bool(_TRANSIENT.search(reason)) and not _QUOTA.search(reason)


def _normalize_patch(patch: str, rel: str, name: str) -> str:
    """Rewrite header paths to the basename form the patch executor expects."""
    patch = patch if patch.endswith("\n") else patch + "\n"
    if rel == name:
        return patch
    lines = []
    for line in patch.splitlines(keepends=True):
        if line.startswith(("diff --git", "--- ", "+++ ")):
            line = line.replace(rel, name)
        lines.append(line)
    return "".join(lines)


def _file_hash(path: Path) -> str:
    return sha256_text(path.read_bytes().decode("utf-8", errors="replace"))


class RemediationEngine:
    def __init__(
        self,
        *,
        project_path: str,
        config: EngineConfig | None = None,
        policy: RepairPolicy | None = None,
        ai_prepare=None,
        store: CandidateStore | None = None,
    ) -> None:
        self.root = Path(project_path).resolve()
        self.config = config or EngineConfig.from_environment()
        self.policy = policy or RepairPolicy()
        self.ai_prepare = ai_prepare
        self.store = store or candidate_store
        self.service = SelfHealService(policy=self.policy)
        self.verifier = SandboxVerifier(timeout_seconds=self.config.sandbox_timeout)
        self.retry = RetryController(max_attempts=self.config.max_attempts)
        self.rollback_controller = RollbackController()
        self.test_command = validate_test_command(
            self.config.test_command or default_test_command(self.config.test_target)
        )
        self._baseline = None
        self.last_analysis: dict | None = None

    # ------------------------------------------------------------ public API
    def remediate(self, *, incident_id: str, diagnostic) -> dict:
        try:
            target = resolve_within(self.root, diagnostic.file_path or "")
            if not diagnostic.file_path or not target.is_file():
                raise ValueError("target file not found")
        except ValueError as exc:
            return self._result("review", f"Repair target is invalid: {exc}")

        problem = self._git_preflight()
        if problem:
            return self._result("review", problem)

        attempts: list[RetryAttempt] = []
        history: list[dict] = []
        tried: set[str] = set()
        feedback = ""
        approved: Candidate | None = None
        last_failure: _Failure | None = None
        notes: list[str] = []
        generation_failures = 0

        while self.retry.can_retry(attempts):
            n = len(attempts) + 1
            proposal = self._propose(diagnostic, target, feedback)
            notes = proposal.notes
            if proposal.patch is None:
                reason = "; ".join(notes) or "No candidate was generated"
                history.append({"attempt": n, "stage": "candidate_generation",
                                "retryable": proposal.retryable, "reason": reason})
                last_failure = _Failure("candidate_generation", reason)
                if proposal.retryable:
                    generation_failures += 1
                    attempts.append(RetryAttempt(
                        attempt=n, passed=False, error=f"candidate_generation: {reason}"))
                    if (generation_failures <= self.config.generation_retries
                            and self.retry.can_retry(attempts)):
                        feedback = f"Attempt {n} failed during candidate generation: {reason}"
                        log.warning("incident=%s transient AI failure, retrying: %s", incident_id, reason)
                        if self.config.retry_backoff > 0:
                            time.sleep(self.config.retry_backoff * generation_failures)
                        continue
                break  # permanent failure (no strategy, quota) or retries used up

            rel = target.relative_to(self.root).as_posix()
            patch = _normalize_patch(proposal.patch, rel, target.name)
            digest = sha256_text(patch)
            if digest in tried:
                last_failure = _Failure("duplicate", "identical candidate already rejected")
                history.append({"attempt": n, "stage": "duplicate", "reason": last_failure.reason})
                break
            tried.add(digest)

            candidate, failure = self._evaluate(
                incident_id, target, rel, patch, proposal, diagnostic
            )
            self.store.save(candidate)  # persist gate results (visible to other processes)
            history.append({
                "attempt": n,
                "source": proposal.source,
                "passed": failure is None,
                "stage": failure.stage if failure else "approved",
                "reason": failure.reason if failure else "all gates passed",
            })
            if failure is None:
                attempts.append(RetryAttempt(attempt=n, passed=True))
                approved = candidate
                break

            attempts.append(RetryAttempt(attempt=n, passed=False, error=f"{failure.stage}: {failure.reason}"))
            last_failure = failure
            log.warning("incident=%s attempt=%d rejected at %s: %s", incident_id, n, failure.stage, failure.reason)
            if failure.terminal:
                return self._result(
                    "review", failure.reason, attempts=history,
                    candidate=candidate, patch=patch, source=proposal.source,
                )
            feedback = f"Attempt {n} was rejected at stage '{failure.stage}': {failure.reason}"

        if approved is None:
            return self._no_candidate_result(attempts, history, last_failure, notes)

        base = dict(
            attempts=history, candidate=approved,
            patch=approved.patch, source=approved.source,
        )
        if not self.config.execute:
            return self._result("approved", "Candidate passed all gates; not executed", **base)

        outcome = self.execute(approved)
        status = "repaired" if outcome["success"] else outcome["status"]
        return self._result(status, outcome.get("error", ""), execution=outcome, **base)

    def execute(self, candidate: Candidate) -> dict:
        """
        Execution boundary. Always works from the REGISTERED record (looked up
        by id), never from the caller's object, re-validates the recorded gate
        state, then runs the transaction.
        """
        stored = self.store.get(candidate.candidate_id)
        if stored is None:
            return {"success": False, "executed": False, "status": "rejected",
                    "error": "Unknown candidate_id"}
        if stored is not candidate and stored.patch_sha256 != candidate.patch_sha256:
            return {"success": False, "executed": False, "status": "rejected",
                    "error": "candidate does not match the registered record"}
        result = self._execute(stored)
        self.store.save(stored)
        return result

    def _execute(self, candidate: Candidate) -> dict:
        problems = self._execution_preconditions(candidate)
        if problems:
            return {"success": False, "executed": False, "status": "rejected",
                    "error": "; ".join(problems)}

        target = Path(candidate.file_path)
        original_bytes = target.read_bytes()
        before = snapshot_files(str(self.root))
        repo = None
        original_branch = branch = None
        git_info: dict | None = None

        if candidate.git_commit:
            repo = GitRepository(self.root)
            original_branch = repo.branch_name()
            branch = f"{self.config.branch_prefix}-{candidate.candidate_id[:8]}"
            created = repo.create_branch(branch)
            git_info = {"branch": branch, "branch_created": created.success, "committed": False}
            if not created.success:
                candidate.status = "failed"
                return {"success": False, "executed": False, "status": "failed",
                        "git": git_info,
                        "error": f"could not create healing branch: {created.stderr.strip()}"}

        try:
            apply_patch(file_path=str(target), patch=candidate.patch, dry_run=False)

            tests = run_tests(project_path=str(self.root), test_command=self.test_command)
            if not tests.passed:
                raise _StepFailed("post-repair tests failed", tests.output)

            after = snapshot_files(str(self.root))
            scope = compare_file_scope(before, after, {candidate.rel_target})
            if not scope.passed:
                raise _StepFailed(f"unapproved files changed: {list(scope.unexpected_files)}")

            if target.read_bytes() == original_bytes:
                raise _StepFailed("patch did not change the target file")

            if repo is not None:
                commit = repo.prepare_commit(f"selfheal: fix {candidate.incident_id[:40]}")
                if not commit.success:
                    raise _StepFailed("git commit failed", commit.stderr or commit.stdout)
                git_info["committed"] = True
        except Exception as exc:  # any failure inside the transaction rolls back
            rollback = self._rollback(repo, original_branch, branch, target, original_bytes)
            candidate.status = "failed"
            status = "rolled_back" if not rollback["errors"] else "rollback_failed"
            log.error("incident=%s execution failed: %s", candidate.incident_id, exc)
            return {
                "success": False, "executed": False, "status": status,
                "error": str(exc), "detail": getattr(exc, "detail", ""),
                "rollback": rollback, "git": git_info,
            }

        candidate.status = "executed"
        log.info("incident=%s repaired via %s", candidate.incident_id, candidate.source)
        return {
            "success": True, "executed": True, "status": "repaired",
            "candidate_id": candidate.candidate_id,
            "tests_passed": True, "test_output": tests.output,
            "changed_files": list(scope.changed_files), "git": git_info,
        }

    # ------------------------------------------------------------- internals
    def _ai_enabled(self) -> bool:
        if self.config.use_ai is False:
            return False
        if self.ai_prepare is not None:
            return True
        from .agents.runner import ai_available
        return ai_available()

    def _propose(self, diagnostic, target: Path, feedback: str) -> _Proposal:
        notes: list[str] = []
        ai_reason = ""
        if self._ai_enabled():
            incident = diagnostic.message
            if feedback:
                incident += f"\n\nFeedback from the previous rejected attempt: {feedback}"
            ai = propose_ai_patch(
                incident=incident, file_path=str(target),
                project_path=str(self.root), prepare=self.ai_prepare,
            )
            if ai["approved"]:
                return _Proposal(ai["patch"], SOURCE_AI, float(ai["confidence"]))
            ai_reason = str(ai.get("reason", ""))
            notes.append(f"AI: {ai_reason}")

        rule = generate_repair_patch(
            file_path=str(target), error_type=diagnostic.error_type,
            message=diagnostic.message, line_number=diagnostic.line_number,
            column=getattr(diagnostic, "column", None),
        )
        if rule:
            return _Proposal(rule, SOURCE_RULE, RULE_BASED_CONFIDENCE, notes)
        return _Proposal(
            None,
            notes=notes or ["No supported repair strategy was available"],
            retryable=bool(ai_reason) and is_transient_ai_failure(ai_reason),
        )

    def _evaluate(self, incident_id, target, rel, patch, proposal, diagnostic):
        """Run every deterministic gate. Returns (candidate, failure|None)."""
        candidate = Candidate(
            incident_id=incident_id, project_path=str(self.root),
            file_path=str(target), rel_target=rel, patch=patch,
            source=proposal.source, confidence=proposal.confidence,
            patch_sha256=sha256_text(patch), target_sha256=_file_hash(target),
            git_commit=self.config.git_commit, test_command=list(self.test_command),
        )
        self.store.add(candidate)

        def reject(stage, reason, terminal=False):
            candidate.status = "needs_review" if terminal else "rejected"
            candidate.notes.append(f"{stage}: {reason}")
            return candidate, _Failure(stage, reason, terminal)

        # 1. structural validation
        verdict = validate_candidate(file_path=str(target), confidence=proposal.confidence, patch=patch)
        if not verdict.valid:
            return reject("validation", "; ".join(verdict.errors))
        try:
            files = parse_patch(patch)
        except Exception as exc:
            return reject("validation", f"unparseable patch: {exc}")
        if len(files) != 1 or files[0].new_path not in {rel, target.name}:
            return reject("scope", "patch must modify exactly the approved target file")
        diffs = parse_diff(patch)
        if len(diffs) != 1:
            return reject("validation", "patch must contain exactly one 'b/' file header")
        candidate.validation_ok = True

        # 2. risk from the REAL diff, then policy gate
        changed = sum(d.additions + d.deletions for d in diffs)
        risk = assess_risk(
            files_changed=len(diffs), lines_changed=changed,
            changed_paths=[d.path for d in diffs],
        )
        candidate.risk = {
            "tier": risk.tier, "files_changed": risk.files_changed,
            "lines_changed": risk.lines_changed,
            "security_sensitive": risk.security_sensitive,
        }
        analysis = self.service.analyze(incident_id=incident_id, risk=risk, tests_available=True)
        self.last_analysis = analysis
        if analysis["decision"].action != "auto_apply":
            return reject("policy", analysis["decision"].reason, terminal=True)
        candidate.policy_allowed = True

        # 3. sandbox: patched temporary copy; the real repository is untouched
        workdir = Path(tempfile.mkdtemp(prefix="selfheal-candidate-"))
        try:
            copy = workdir / "project"
            shutil.copytree(self.root, copy, ignore=COPY_IGNORE)
            try:
                apply_patch(file_path=str(copy / rel), patch=patch, dry_run=False)
            except (ValueError, FileNotFoundError) as exc:
                return reject("sandbox", f"patch does not apply: {exc}")

            gate = check_rewrite(
                rel, target.read_text(encoding="utf-8"),
                (copy / rel).read_text(encoding="utf-8"),
            )
            if not gate.ok:
                return reject("security_gate", "; ".join(gate.reasons))

            ver = self.verifier.verify(repository_path=copy, command=self.test_command)
            result = ver.sandbox_result
            if not ver.passed:
                why = "sandbox timed out" if result.timed_out else (result.stdout + result.stderr)[-400:]
                return reject("sandbox", f"verification failed in isolated copy: {why.strip()}")
            candidate.sandbox_passed = True
            cand_check = CheckResult(
                name="pytest", passed=True, return_code=result.return_code,
                stdout=result.stdout, stderr=result.stderr,
            )
            cand_files = snapshot_files(str(copy))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        # 4. regression gate (real baseline vs real candidate results)
        base_check, base_files = self._get_baseline()
        regression = RegressionGate().evaluate(
            baseline_checks=[base_check], candidate_checks=[cand_check],
            baseline_files=base_files, candidate_files=cand_files,
            approved_files={rel},
        )
        if not regression.passed:
            return reject("regression", "; ".join(regression.reasons))
        candidate.regression_passed = True

        candidate.status = "approved"
        return candidate, None

    def _get_baseline(self):
        if self._baseline is None:
            ver = self.verifier.verify(repository_path=self.root, command=self.test_command)
            r = ver.sandbox_result
            self._baseline = (
                CheckResult(name="pytest", passed=ver.passed, return_code=r.return_code,
                            stdout=r.stdout, stderr=r.stderr),
                snapshot_files(str(self.root)),
            )
        return self._baseline

    def _git_preflight(self) -> str | None:
        if not self.config.git_commit:
            return None
        try:
            repo = GitRepository(self.root)
        except FileNotFoundError:
            return "git_commit requires an existing project directory"
        if not repo.is_repository():
            return "git_commit requires a Git repository"
        if repo.has_tracked_changes():
            return "working tree has uncommitted changes"
        if not repo.branch_name():
            return "detached HEAD is not supported for git_commit"
        return None

    def _execution_preconditions(self, c: Candidate) -> list[str]:
        problems: list[str] = []
        if c.status != "approved":
            problems.append(f"candidate status is '{c.status}', not 'approved'")
        for flag in ("validation_ok", "policy_allowed", "sandbox_passed", "regression_passed"):
            if not getattr(c, flag):
                problems.append(f"gate not passed: {flag}")
        if sha256_text(c.patch) != c.patch_sha256:
            problems.append("patch was modified after approval")
        try:
            target = resolve_within(self.root, c.file_path)
            if target.relative_to(self.root).as_posix() != c.rel_target:
                problems.append("target does not match the approved target")
            elif not target.is_file():
                problems.append("target file no longer exists")
            elif _file_hash(target) != c.target_sha256:
                problems.append("target file changed since approval (stale candidate)")
            files = parse_patch(c.patch)
            if len(files) != 1 or files[0].new_path not in {c.rel_target, target.name}:
                problems.append("patch target does not match the approved target")
        except (ValueError, OSError) as exc:
            problems.append(str(exc))
        problem = self._git_preflight()
        if problem:
            problems.append(problem)
        return problems

    def _rollback(self, repo, original_branch, branch, target: Path, original_bytes: bytes) -> dict:
        errors: list[str] = []
        try:
            target.write_bytes(original_bytes)
        except OSError as exc:
            errors.append(f"file restore failed: {exc}")
        git_clean = None
        if repo is not None:
            reset = repo.rollback()
            if not reset.success:
                errors.append(f"git reset failed: {reset.stderr.strip()}")
            if original_branch:
                back = repo.checkout(original_branch)
                if not back.success:
                    errors.append(f"could not return to '{original_branch}': {back.stderr.strip()}")
                elif branch:
                    dele = repo.delete_branch(branch)
                    if not dele.success:
                        errors.append(f"could not delete '{branch}': {dele.stderr.strip()}")
            git_clean = not repo.has_tracked_changes()
        return {"performed": True, "errors": errors, "git_clean": git_clean,
                "restored_branch": original_branch}

    def _no_candidate_result(self, attempts, history, last_failure, notes) -> dict:
        if not attempts:  # nothing was ever evaluated
            reason = "; ".join(notes) if notes else "No supported repair strategy was available"
            return self._result("review", reason, attempts=history)

        stage = last_failure.stage if last_failure else ""
        decision = self.rollback_controller.evaluate(
            verification_passed=stage not in {"validation", "security_gate", "scope", "sandbox"},
            regression_passed=stage != "regression",
            retry_exhausted=True,
            policy_accepted=True,
        )
        exhausted = self.retry.record(attempts).exhausted
        rollback = {
            "required": decision.required,
            "reason": decision.reason.value if decision.reason else None,
            "repository_modified": False,
            "action": "none_needed: candidates are only applied in isolated copies until approved",
        }
        if self.config.git_commit:
            repo = GitRepository(self.root)
            rollback["git_clean"] = not repo.has_tracked_changes()
        if last_failure and last_failure.stage == "candidate_generation":
            message = (f"Candidate generation failed after {len(attempts)} "
                       f"attempt(s): {last_failure.reason}")
        else:
            message = f"No candidate passed all gates after {len(attempts)} attempt(s)"
        return self._result(
            "exhausted" if exhausted else "review", message,
            attempts=history, rollback=rollback,
        )

    def _result(self, status: str, reason: str = "", *, candidate: Candidate | None = None,
                patch: str | None = None, source: str | None = None, **extra) -> dict:
        out = {"status": status, "reason": reason}
        if candidate is not None:
            out["candidate_id"] = candidate.candidate_id
            out["candidate"] = candidate.public()
        if patch is not None:
            out["patch"] = patch
        if source is not None:
            out["patch_source"] = source
        out.update(extra)
        return out


class _StepFailed(Exception):
    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail[-800:]


def execute_candidate(candidate_id: str, *, store: CandidateStore | None = None) -> dict:
    """Execute a previously approved candidate by id (the only execution entry for MCP)."""
    store = store or candidate_store
    candidate = store.get(candidate_id)
    if candidate is None:
        return {"success": False, "executed": False, "status": "rejected",
                "error": "Unknown candidate_id"}
    engine = RemediationEngine(
        project_path=candidate.project_path,
        config=EngineConfig.from_environment(
            git_commit=candidate.git_commit, test_command=candidate.test_command or None
        ),
        store=store,
    )
    return engine.execute(candidate)
