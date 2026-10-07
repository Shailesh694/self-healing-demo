from __future__ import annotations

from pathlib import Path

from .analysis.scorer import assess_risk
from .candidates import CandidateStore
from .ci import parse_ci_result
from .diagnostics import diagnose
from .engine import RULE_BASED_CONFIDENCE, EngineConfig, RemediationEngine  # noqa: F401
from .logger import get_logger
from .policy import RepairPolicy
from .service import SelfHealService

log = get_logger("selfheal.workflow")


def process_ci_failure(
    payload: dict,
    *,
    incident_id: str,
    provider: str = "generic",
    project_path: str = ".",
    policy: RepairPolicy | None = None,
    ai_prepare=None,
    diagnostic=None,
    store: CandidateStore | None = None,
) -> dict:
    """
    Entry point shared by the webhook, the CI runner and MCP.

    It parses and diagnoses the failure, then hands the remediation to
    RemediationEngine, which owns every gate, retry, Git and rollback step.
    Automatic modification stays disabled unless the policy allows it.

    Payload flags: git_commit (commit on a healing branch), execute (default
    True; False stops after the candidate is approved), use_agents (False
    disables the AI path).
    """
    ci_result = parse_ci_result(payload, provider=provider)
    if ci_result.success:
        return {"status": "ignored", "reason": "CI run was successful"}

    if diagnostic is None:
        diagnostic = diagnose(ci_result.logs)

    if diagnostic.file_path and not Path(diagnostic.file_path).is_absolute():
        candidate_path = Path(project_path) / diagnostic.file_path
        if candidate_path.exists():
            diagnostic.file_path = str(candidate_path)

    log.info(
        "incident=%s diagnosed type=%s file=%s line=%s",
        incident_id, diagnostic.error_type, diagnostic.file_path, diagnostic.line_number,
    )

    repair_policy = policy or RepairPolicy()
    result = {"status": "diagnosed", "ci": ci_result, "diagnostic": diagnostic}

    if not repair_policy.allow_auto_apply:
        # Preliminary assessment only: no patch exists yet, so risk is a
        # path-based estimate. The authoritative risk is computed from the
        # real diff of each candidate inside the engine.
        preliminary = SelfHealService(policy=repair_policy).analyze(
            incident_id=incident_id,
            risk=assess_risk(
                files_changed=1, lines_changed=1,
                changed_paths=[diagnostic.file_path] if diagnostic.file_path else [],
            ),
            tests_available=True,
        )
        preliminary["preliminary"] = True
        result["analysis"] = preliminary
        result["reason"] = "Automatic repair is disabled by policy"
        return result

    if not diagnostic.file_path:
        result["status"] = "review"
        result["reason"] = "Repair target file could not be determined"
        return result

    config = EngineConfig.from_environment(
        git_commit=bool(payload.get("git_commit", False)),
        execute=bool(payload.get("execute", True)),
        use_ai=payload.get("use_agents"),
    )
    if payload.get("test_command"):
        config.test_command = list(payload["test_command"])

    try:
        engine = RemediationEngine(
            project_path=project_path, config=config, policy=repair_policy,
            ai_prepare=ai_prepare, store=store,
        )
        outcome = engine.remediate(incident_id=incident_id, diagnostic=diagnostic)
    except Exception as exc:  # invalid config/command etc.: fail safely, never crash
        log.exception("incident=%s engine error", incident_id)
        result["status"] = "error"
        result["reason"] = str(exc)
        return result

    execution = outcome.get("execution") or {}
    result["repair"] = {**execution, **{k: v for k, v in outcome.items() if k != "execution"}}
    if execution.get("git") is not None:
        result["repair"]["git"] = execution["git"]
    result["analysis"] = engine.last_analysis
    if "candidate_id" in outcome:
        result["candidate_id"] = outcome["candidate_id"]
    result["status"] = outcome["status"]
    result["reason"] = outcome.get("reason", "")
    if "patch" in outcome:
        result["candidate_patch"] = outcome["patch"]
    if "patch_source" in outcome:
        result["patch_source"] = outcome["patch_source"]
    log.info("incident=%s status=%s", incident_id, result["status"])
    return result
