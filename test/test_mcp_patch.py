import sys
from pathlib import Path

import pytest
from selfheal.mcp.server import mcp_server

from selfheal.agents.gemini import (
    GeminiClient,
    GeminiResult,
)
from selfheal.config import SelfHealConfig
from unittest.mock import MagicMock, patch

from selfheal.mcp.tools import (
    diagnose_incident,
    execute_repair_candidate,
    generate_patch,
    generate_repair_candidate,
    review_repair_candidate,
    rollback,
    run_remediation,
    survey_repository,
    verify_patch,
    verify_repair_candidate,
    get_remediation_status,
    evaluate_agent_repair_candidate,
)

VALID_PATCH = (
    "diff --git a/app.py b/app.py\n"
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1 +1 @@\n"
    "-print('old')\n"
    "+print('new')\n"
)


def test_generate_patch_returns_candidate():
    result = generate_patch(
        file_path="app.py",
        problem="Replace incorrect output",
        confidence=0.9,
        patch=VALID_PATCH,
    )

    assert result["file_path"] == "app.py"
    assert result["confidence"] == 0.9
    assert result["patch"] == VALID_PATCH
    assert "Proposed repair" in result["description"]


def test_generate_patch_does_not_modify_file(
    tmp_path: Path,
):
    file_path = tmp_path / "app.py"

    original = "print('old')\n"

    file_path.write_text(
        original,
        encoding="utf-8",
    )

    generate_patch(
        file_path=str(file_path),
        problem="Replace output",
        confidence=0.9,
        patch=VALID_PATCH.replace(
            "a/app.py",
            f"a/{file_path}",
        ).replace(
            "b/app.py",
            f"b/{file_path}",
        ),
    )

    assert file_path.read_text(
        encoding="utf-8"
    ) == original


def test_generate_patch_rejects_empty_file_path():
    with pytest.raises(ValueError):
        generate_patch(
            file_path="",
            problem="Fix problem",
            confidence=0.9,
            patch=VALID_PATCH,
        )


def test_generate_patch_rejects_empty_problem():
    with pytest.raises(ValueError):
        generate_patch(
            file_path="app.py",
            problem="",
            confidence=0.9,
            patch=VALID_PATCH,
        )


def test_verify_patch_accepts_valid_patch():
    result = verify_patch(
        file_path="app.py",
        confidence=0.9,
        patch=VALID_PATCH,
    )

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["patch_provided"] is True


def test_verify_patch_rejects_missing_patch():
    result = verify_patch(
        file_path="app.py",
        confidence=0.9,
        patch=None,
    )

    assert result["valid"] is False
    assert "No patch was provided" in result["errors"]


def test_verify_patch_rejects_empty_patch():
    result = verify_patch(
        file_path="app.py",
        confidence=0.9,
        patch="",
    )

    assert result["valid"] is False
    assert "Patch cannot be empty" in result["errors"]


def test_verify_patch_rejects_invalid_confidence():
    result = verify_patch(
        file_path="app.py",
        confidence=1.5,
        patch=VALID_PATCH,
    )

    assert result["valid"] is False
    assert (
        "Confidence must be between 0.0 and 1.0"
        in result["errors"]
    )


def test_verify_patch_rejects_multiple_files():
    patch = (
        VALID_PATCH
        + "\n"
        + "diff --git a/other.py b/other.py\n"
        + "--- a/other.py\n"
        + "+++ b/other.py\n"
        + "@@ -1 +1 @@\n"
        + "-old\n"
        + "+new\n"
    )

    result = verify_patch(
        file_path="app.py",
        confidence=0.9,
        patch=patch,
    )

    assert result["valid"] is False
    assert (
        "Patch must modify exactly one file"
        in result["errors"]
    )


def test_verify_patch_rejects_wrong_target():
    patch = VALID_PATCH.replace(
        "a/app.py",
        "a/other.py",
    ).replace(
        "b/app.py",
        "b/other.py",
    )

    result = verify_patch(
        file_path="app.py",
        confidence=0.9,
        patch=patch,
    )

    assert result["valid"] is False
    assert (
        "Patch target does not match "
        "the candidate file path"
        in result["errors"]
    )


def test_verify_patch_rejects_empty_file_path():
    with pytest.raises(ValueError):
        verify_patch(
            file_path="",
            confidence=0.9,
            patch=VALID_PATCH,
        )


def test_mcp_server_registers_patch_tools():
    tools = mcp_server._tool_manager.list_tools()

    names = {
        tool.name
        for tool in tools
    }

    assert "generate_patch" in names
    assert "verify_patch" in names

def test_run_remediation_accepts_verified_candidate():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
    )

    assert result["accepted"] is True
    assert result["status"] == "accepted"
    assert result["requires_human_review"] is False
    assert result["exhausted"] is False
    assert len(result["attempts"]) == 1

def test_run_remediation_rejects_failed_verification():
    result = run_remediation(
        attempt=1,
        verification_passed=False,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
        error="verification failed",
    )

    assert result["accepted"] is False
    assert result["status"] in {
        "rejected",
        "human_review_required",
        "exhausted",
    }
    assert result["attempts"][0]["verification_passed"] is False

def test_run_remediation_requires_human_review_for_high_risk():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="HIGH",
        auto_heal=True,
    )

    assert result["status"] == "human_review_required"
    assert result["accepted"] is False
    assert result["requires_human_review"] is True
    assert result["policy"]["accepted"] is False
    assert result["policy"]["requires_human_review"] is True

def test_run_remediation_requires_human_review_for_critical_risk():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="CRITICAL",
        auto_heal=True,
    )

    assert result["status"] == "human_review_required"
    assert result["accepted"] is False
    assert result["requires_human_review"] is True
    assert result["policy"]["accepted"] is False
    assert result["policy"]["requires_human_review"] is True

def test_rollback_requires_failed_remediation():
    result = rollback(
        verification_passed=False,
        regression_passed=False,
        retry_exhausted=True,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] is not None

def test_diagnose_incident_returns_scope(
    tmp_path: Path,
):
    repository = tmp_path / "repo"
    app_dir = repository / "app"

    app_dir.mkdir(parents=True)

    (app_dir / "service.py").write_text(
        "def run():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    from selfheal.models import Incident
    from selfheal.runtime import incident_manager

    incident = Incident(
        source="pytest",
        code="PYTEST_FAILURE",
        message="test failure",
        file_path="app/service.py",
        line=2,
        column=None,
    )

    incident_manager.create(incident)

    records = incident_manager.list_open()

    assert records

    fingerprint = None

    for record in records:
        if record.incident == incident:
            from selfheal.incidents.fingerprint import (
                IncidentFingerprinter,
            )

            fingerprint = (
                IncidentFingerprinter().fingerprint(
                    incident
                )
            )
            break

    assert fingerprint is not None

    result = diagnose_incident(
        fingerprint,
        str(repository),
    )

    assert result["found"] is True
    assert result["fingerprint"] == fingerprint
    assert result["diagnosis"]["incident"]["file_path"] == (
        "app/service.py"
    )
    assert result["diagnosis"]["scope"]["file_path"] == (
        "app/service.py"
    )

def test_survey_repository_returns_context(
    tmp_path: Path,
):
    repository = tmp_path / "repo"
    app_dir = repository / "app"

    app_dir.mkdir(parents=True)

    (app_dir / "service.py").write_text(
        "def run():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    result = survey_repository(
        str(repository),
        "app/service.py",
    )

    assert result["file_path"] == "app/service.py"
    assert result["survey"]["target_exists"] is True
    assert "dependencies" in result["survey"]
    assert "related_tests" in result["survey"]
    assert "symbols" in result["survey"]
    assert "imports" in result["survey"]


def test_generate_repair_candidate_combines_survey_and_patch(
    tmp_path: Path,
):
    repository = tmp_path / "repo"
    app_dir = repository / "app"

    app_dir.mkdir(parents=True)

    (app_dir / "service.py").write_text(
        "def run():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    result = generate_repair_candidate(
        repository_path=str(repository),
        file_path="app/service.py",
        problem="return value is incorrect",
        confidence=0.9,
        patch=None,
    )

    assert result["file_path"] == "app/service.py"
    assert result["problem"] == (
        "return value is incorrect"
    )
    assert "survey" in result
    assert "candidate" in result
    assert result["survey"]["target_exists"] is True
    assert result["candidate"]["file_path"] == (
        "app/service.py"
    )


def test_verify_repair_candidate_hands_off_to_validator():
    candidate = {
        "file_path": "app.py",
        "confidence": 0.9,
        "patch": VALID_PATCH,
    }

    result = verify_repair_candidate(candidate)

    assert result["file_path"] == (
        "app.py"
    )
    assert result["confidence"] == 0.9
    assert result["patch_provided"] is True
    assert result["valid"] is True
    assert result["errors"] == []

def test_review_repair_candidate_returns_reviewer_finding():
    mock_response = MagicMock()

    mock_response.text = """
    {
        "approved": false,
        "risk_level": "HIGH",
        "issues": [
            "Patch changes behavior outside the incident scope."
        ],
        "required_changes": [
            "Limit the patch to the failing expression."
        ],
        "explanation": "The proposed change is broader than necessary.",
        "confidence": 0.96
    }
    """

    from selfheal.agents.reviewer import ReviewFinding

    finding = ReviewFinding(
        approved=False,
        risk_level="HIGH",
        issues=[
            "Patch changes behavior outside the incident scope."
        ],
        required_changes=[
            "Limit the patch to the failing expression."
        ],
        explanation=(
            "The proposed change is broader than necessary."
        ),
        confidence=0.96,
    )

    mock_gemini = MagicMock()

    mock_gemini.generate_json.return_value = GeminiResult(
        success=True,
        response=finding,
    )

    with patch(
        "selfheal.mcp.tools.GeminiClient",
        return_value=mock_gemini,
    ):
        result = review_repair_candidate(
            incident="NameError: name 'foo' is not defined",
            surveyor_finding="Undefined variable foo",
            proposed_patch=(
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@ -1 +1 @@\n"
                "-print(foo)\n"
                "+modify_entire_application()\n"
            ),
            repository_context="print(foo)",
        )

    assert result["success"] is True
    assert result["approved"] is False
    assert result["risk_level"] == "HIGH"
    assert result["issues"]
    assert result["required_changes"]
    assert result["confidence"] == 0.96

def test_execute_repair_candidate_dry_run(
    tmp_path: Path,
):
    target = tmp_path / "app.py"

    target.write_text(
        "print('old')\n",
        encoding="utf-8",
    )

    patch = (
        f"diff --git a/{target.name} b/{target.name}\n"
        f"--- a/{target.name}\n"
        f"+++ b/{target.name}\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )

    result = execute_repair_candidate(
        file_path=str(target),
        patch=patch,
        dry_run=True,
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["applied"] is True
    assert target.read_text(
        encoding="utf-8"
    ) == "print('old')\n"

def test_run_remediation_rejects_failed_regression():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=False,
        risk_level="LOW",
        auto_heal=True,
        error="regression failed",
    )

    assert result["accepted"] is False
    assert result["requires_human_review"] is False
    assert result["attempts"][0]["regression_passed"] is False
    assert result["attempts"][0]["policy"]["accepted"] is False

def test_execute_repair_candidate_applies_patch(
    tmp_path: Path,
):
    target = tmp_path / "app.py"

    target.write_text(
        "print('old')\n",
        encoding="utf-8",
    )

    patch = (
        f"diff --git a/{target.name} b/{target.name}\n"
        f"--- a/{target.name}\n"
        f"+++ b/{target.name}\n"
        "@@ -1 +1 @@\n"
        "-print('old')\n"
        "+print('new')\n"
    )

    result = execute_repair_candidate(
        file_path=str(target),
        patch=patch,
        dry_run=False,
    )

    assert result["success"] is True
    assert result["dry_run"] is False
    assert result["applied"] is True
    assert target.read_text(
        encoding="utf-8"
    ) == "print('new')\n"

def test_execute_repair_candidate_rejects_invalid_patch(
    tmp_path: Path,
):
    target = tmp_path / "app.py"

    target.write_text(
        "print('old')\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        execute_repair_candidate(
            file_path=str(target),
            patch="invalid patch",
            dry_run=False,
        )


def test_run_remediation_rejects_failed_execution():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
        error="patch execution failed",
    )

    assert result["accepted"] is False
    assert result["attempts"][0]["verification_passed"] is False
    assert result["attempts"][0]["policy"]["accepted"] is False

def test_run_remediation_accepts_successful_execution():
    result = run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is True
    assert result["requires_human_review"] is False
    assert result["attempts"][0]["verification_passed"] is True
    assert result["attempts"][0]["regression_passed"] is True
    assert result["attempts"][0]["policy"]["accepted"] is True

def test_run_remediation_reports_exhaustion():
    result = run_remediation(
        attempt=3,
        verification_passed=False,
        regression_passed=False,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
        error="repair failed",
    )

    assert result["accepted"] is False
    assert result["exhausted"] is True
    assert result["requires_human_review"] is False

def test_rollback_after_retry_exhaustion():
    result = rollback(
        verification_passed=False,
        regression_passed=False,
        retry_exhausted=True,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] is not None

def test_rollback_not_required_for_successful_remediation():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is False

def test_get_remediation_status_returns_latest_result():
    run_remediation(
        attempt=1,
        verification_passed=True,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    result = get_remediation_status()

    assert result["status"] == "accepted"
    assert result["result"] is not None
    assert result["result"]["accepted"] is True

def test_evaluate_agent_repair_candidate_rejects_failed_candidate():
    result = evaluate_agent_repair_candidate(
        candidate={
            "success": False,
            "stage": "candidate_generation",
            "error": "Coder did not produce a patch.",
        },
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
    )

    assert result["accepted"] is False
    assert result["stage"] == "candidate_verification"

def test_evaluate_agent_repair_candidate_accepts_valid_candidate():
    result = evaluate_agent_repair_candidate(
        candidate={
            "success": True,
            "verification": {
                "valid": True,
            },
            "patch": "--- a/example.py\n+++ b/example.py",
        },
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is True
    assert result["candidate"]["success"] is True

def test_evaluate_agent_repair_candidate_rejects_failed_execution():
    result = evaluate_agent_repair_candidate(
        candidate={
            "success": True,
            "verification": {
                "valid": True,
            },
            "patch": "--- a/example.py\n+++ b/example.py",
        },
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
        error="patch execution failed",
    )

    assert result["accepted"] is False

def test_evaluate_agent_repair_candidate_rejects_regression_failure():
    result = evaluate_agent_repair_candidate(
        candidate={
            "success": True,
            "verification": {
                "valid": True,
            },
            "patch": "--- a/example.py\n+++ b/example.py",
        },
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
        regression_inputs={
            "baseline_checks": [
                {
                     "name": "unit_tests",
                    "passed": True,
                    "return_code": 0,
                },
            ],
            "candidate_checks": [
                {
                    "name": "unit_tests",
                    "passed": False,
                    "return_code": 1,
                },
            ],
        },
    )

    assert result["accepted"] is False


def test_evaluate_agent_repair_candidate_requires_review_for_high_risk():
    result = evaluate_agent_repair_candidate(
        candidate={
            "success": True,
            "verification": {
                "valid": True,
            },
            "patch": "--- a/example.py\n+++ b/example.py",
        },
        attempt=1,
        risk_level="HIGH",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is False
    assert result["requires_human_review"] is True

def test_evaluate_agent_repair_candidate_requires_review_when_auto_heal_disabled():
    result = evaluate_agent_repair_candidate(
        candidate={
            "success": True,
            "verification": {
                "valid": True,
            },
            "patch": "--- a/example.py\n+++ b/example.py",
        },
        attempt=1,
        risk_level="LOW",
        auto_heal=False,
        execution_passed=True,
    )

    assert result["accepted"] is False
    assert result["requires_human_review"] is True

def test_evaluate_agent_repair_candidate_exhausts_retries():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": "--- a/example.py\n+++ b/example.py",
    }

    results = []

    for attempt in range(1, 4):
        results.append(
            evaluate_agent_repair_candidate(
                candidate=candidate,
                attempt=attempt,
                risk_level="LOW",
                auto_heal=True,
                execution_passed=False,
                error="patch execution failed",
            )
        )

    assert all(
        result["accepted"] is False
        for result in results
    )

    assert results[-1]["exhausted"] is True

def test_rollback_after_failed_remediation():
    result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "VERIFICATION_FAILURE"

def test_failed_retries_require_rollback():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": "--- a/example.py\n+++ b/example.py",
    }

    final_result = None

    for attempt in range(1, 4):
        final_result = evaluate_agent_repair_candidate(
            candidate=candidate,
            attempt=attempt,
            risk_level="LOW",
            auto_heal=True,
            execution_passed=False,
            error="patch execution failed",
        )

    assert final_result is not None
    assert final_result["accepted"] is False
    assert final_result["exhausted"] is True

    rollback_result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=final_result["exhausted"],
        policy_accepted=False,
    )

    assert rollback_result["rollback_required"] is True
    assert rollback_result["reason"] == "VERIFICATION_FAILURE"

def test_policy_rejection_requires_rollback():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "POLICY_REJECTION"

def test_agent_candidate_full_success_path():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": "--- a/app.py\n+++ b/app.py\n@@\n-print('bad')\n+print('good')",
        "confidence": 0.95,
        "target_files": ["app.py"],
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is True
    assert result["requires_human_review"] is False
    assert result["exhausted"] is False


def test_agent_candidate_high_risk_does_not_auto_accept():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": "--- a/app.py\n+++ b/app.py\n@@\n-print('bad')\n+print('good')",
        "confidence": 0.95,
        "target_files": ["app.py"],
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="HIGH",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is False
    assert result["requires_human_review"] is True


def test_agent_candidate_failed_verification_does_not_accept():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": "--- a/app.py\n+++ b/app.py\n@@\n-print('bad')\n+print('good')",
        "confidence": 0.95,
        "target_files": ["app.py"],
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
    )

    assert result["accepted"] is False

def test_accepted_candidate_can_be_sent_to_execution():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": "--- a/app.py\n+++ b/app.py\n@@\n-print('bad')\n+print('good')",
        "confidence": 0.95,
        "target_files": ["app.py"],
    }

    evaluation = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    assert evaluation["accepted"] is True
    assert evaluation["candidate"]["success"] is True


def test_failed_candidate_must_not_reach_execution():
    candidate = {
        "success": False,
        "stage": "candidate_verification",
        "error": "Invalid patch",
    }

    evaluation = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
    )

    assert evaluation["accepted"] is False
    assert evaluation["stage"] == "candidate_verification"


def test_execution_failure_blocks_acceptance_even_when_candidate_is_valid():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": "--- a/app.py\n+++ b/app.py\n@@\n-print('bad')\n+print('good')",
        "confidence": 0.95,
        "target_files": ["app.py"],
    }

    evaluation = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
    )

    assert evaluation["accepted"] is False
    assert evaluation["requires_human_review"] is False

def test_accepted_candidate_does_not_require_rollback():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is False
    assert result["reason"] is None


def test_execution_failure_requires_rollback():
    result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "VERIFICATION_FAILURE"


def test_regression_failure_requires_rollback():
    result = rollback(
        verification_passed=True,
        regression_passed=False,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "REGRESSION_FAILURE"

def test_failed_attempt_can_be_retried():
    first = run_remediation(
        attempt=1,
        verification_passed=False,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
    )

    assert first["accepted"] is False
    assert first["exhausted"] is False


def test_third_failed_attempt_exhausts_retries():
    result = run_remediation(
        attempt=3,
        verification_passed=False,
        regression_passed=True,
        risk_level="LOW",
        auto_heal=True,
    )

    assert result["accepted"] is False
    assert result["exhausted"] is True


def test_exhausted_retry_requires_rollback():
    result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=True,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "VERIFICATION_FAILURE"

def test_evaluate_agent_repair_candidate_marks_success_as_execution_ready():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is True
    assert result["execution_ready"] is True

def test_evaluate_agent_repair_candidate_rejects_failed_candidate_second_variant():
    candidate = {
        "success": False,
        "error": "Coder did not produce a patch.",
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is not True

def test_candidate_is_not_execution_ready_when_auto_heal_disabled():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=False,
        execution_passed=True,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False

def test_sandbox_failure_blocks_execution_ready(
    tmp_path: Path,
):
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
        sandbox_inputs={
            "repository_path": str(tmp_path),
            "command": [sys.executable, "-m", "pytest", ".", "-q"],  # no tests -> nonzero exit
        },
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False

def test_regression_failure_blocks_execution_ready():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
        regression_inputs={
            "baseline_checks": [
                {
                    "name": "pytest",
                    "passed": True,
                    "return_code": 0,
                },
            ],
            "candidate_checks": [
                {
                    "name": "pytest",
                    "passed": False,
                    "return_code": 1,
                },
            ],
            "baseline_files": [],
            "candidate_files": [],
            "approved_files": [],
        },
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False

def test_successful_sandbox_keeps_candidate_execution_ready(
    tmp_path: Path,
):
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n")

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
        sandbox_inputs={
            "repository_path": str(tmp_path),
            "command": [sys.executable, "-m", "pytest", ".", "-q"],
        },
    )

    assert result["accepted"] is True
    assert result["execution_ready"] is True

def test_accepted_candidate_is_execution_ready():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is True
    assert result["execution_ready"] is True

def test_failed_execution_prevents_execution_ready():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False

def test_high_risk_candidate_requires_human_review():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="HIGH",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False

def test_rollback_required_after_verification_failure():
    result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "VERIFICATION_FAILURE"

def test_rollback_required_after_regression_failure():
    result = rollback(
        verification_passed=True,
        regression_passed=False,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "REGRESSION_FAILURE"

def test_successful_remediation_does_not_require_rollback():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert result["rollback_required"] is False
    assert result["reason"] is None

def test_third_failed_attempt_is_exhausted():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=3,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False
    assert result["exhausted"] is True

def test_first_failed_attempt_is_not_exhausted():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False
    assert result["exhausted"] is False

def test_invalid_candidate_cannot_be_execution_ready():
    candidate = {
        "success": False,
        "error": "Coder did not produce a patch.",
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=1,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=True,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False

def test_exhausted_remediation_requires_rollback():
    candidate = {
        "success": True,
        "verification": {
            "valid": True,
        },
        "patch": VALID_PATCH,
    }

    result = evaluate_agent_repair_candidate(
        candidate=candidate,
        attempt=3,
        risk_level="LOW",
        auto_heal=True,
        execution_passed=False,
    )

    assert result["accepted"] is False
    assert result["execution_ready"] is False
    assert result["exhausted"] is True

    rollback_result = rollback(
        verification_passed=False,
        regression_passed=True,
        retry_exhausted=result["exhausted"],
        policy_accepted=True,
    )

    assert rollback_result["rollback_required"] is True
    assert rollback_result["reason"] == "VERIFICATION_FAILURE"

def test_policy_rejection_requires_rollback_second_variant():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=False,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "POLICY_REJECTION"

def test_retry_exhaustion_requires_rollback():
    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=True,
        policy_accepted=True,
    )

    assert result["rollback_required"] is True
    assert result["reason"] == "RETRY_EXHAUSTED"

def test_successful_execution_does_not_require_rollback():
    execution_passed = True

    result = rollback(
        verification_passed=True,
        regression_passed=True,
        retry_exhausted=False,
        policy_accepted=True,
    )

    assert execution_passed is True
    assert result["rollback_required"] is False
    assert result["reason"] is None

