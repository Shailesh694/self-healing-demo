from __future__ import annotations

from .analysis.repair_strategy import generate_repair_patch
from .analysis.scorer import assess_risk
from .ci import parse_ci_result
from .diagnostics import diagnose
from .service import SelfHealService
from .policy import RepairPolicy


def process_ci_failure(
    payload: dict,
    *,
    incident_id: str,
    provider: str = "generic",
    project_path: str = ".",
    policy: RepairPolicy | None = None,
) -> dict:
    """
    Process a CI failure through the SelfHeal workflow.

    The default policy keeps automatic modification disabled.
    When auto-apply is explicitly enabled, a supported repair
    candidate can proceed through the repair/verification engine.
    """

    ci_result = parse_ci_result(
        payload,
        provider=provider,
    )

    if ci_result.success:
        return {
            "status": "ignored",
            "reason": "CI run was successful",
        }

    diagnostic = diagnose(
        ci_result.logs,
    )

    risk = assess_risk(
        files_changed=1,
        lines_changed=1,
        changed_paths=(
            [diagnostic.file_path]
            if diagnostic.file_path
            else []
        ),
    )

    repair_policy = policy or RepairPolicy()

    service = SelfHealService(
        policy=repair_policy,
    )

    analysis = service.analyze(
        incident_id=incident_id,
        risk=risk,
        tests_available=True,
    )

    result = {
        "status": "diagnosed",
        "ci": ci_result,
        "diagnostic": diagnostic,
        "analysis": analysis,
    }

    if analysis["decision"].action != "auto_apply":
        return result

    if not diagnostic.file_path:
        result["status"] = "review"
        result["reason"] = (
            "Repair target file could not be determined"
        )
        return result

    patch = generate_repair_patch(
        file_path=diagnostic.file_path,
        error_type=diagnostic.error_type,
        message=diagnostic.message,
        line_number=diagnostic.line_number,
    )

    if patch is None:
        result["status"] = "review"
        result["reason"] = (
            "No supported repair strategy was available"
        )
        return result

    result["candidate_patch"] = patch

    from .analysis.repair import repair_and_verify

    repair_result = repair_and_verify(
        file_path=diagnostic.file_path,
        problem=diagnostic.message,
        confidence=0.95,
        patch=patch,
        project_path=project_path,
    )

    result["repair"] = repair_result

    if repair_result["status"] == "repaired":
        result["status"] = "repaired"
    elif repair_result["status"] == "rolled_back":
        result["status"] = "rolled_back"

    return result