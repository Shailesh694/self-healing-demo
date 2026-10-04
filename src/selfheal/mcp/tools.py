from pathlib import Path
from typing import Any

from selfheal.regression import CheckResult
from selfheal.agents.orchestrator import AgentOrchestrator
from selfheal.agents.surveyor import SurveyorAgent
from selfheal.agents.coder import CoderAgent
from selfheal.sandbox import SandboxVerifier
from selfheal.regression_runner import evaluate_regression
from selfheal.regression_scope import FileSnapshot
from selfheal.analysis.executor import apply_patch
from selfheal.analysis.ast import PythonASTAnalyzer
from selfheal.analysis.generator import generate_candidate
from selfheal.analysis.validator import validate_candidate
from selfheal.runtime import incident_manager
from selfheal.incidents.fingerprint import IncidentFingerprinter
from selfheal.agents.reviewer import AdversarialReviewer
from selfheal.agents.gemini import GeminiClient
from selfheal.config import SelfHealConfig
from selfheal.risk import assess_risk
from selfheal.remediation_controller import (
    RemediationAttemptResult,
    RemediationController,
)
from selfheal.repository.index import RepositoryIndex
from selfheal.repository.scanner import (
    scan_repository as repository_scan,
    summarize_by_language,
)
from selfheal.risk import RiskLevel
from selfheal.rollback_controller import RollbackController


incident_fingerprinter = IncidentFingerprinter()

remediation_controller = RemediationController()
rollback_controller = RollbackController()

sandbox_verifier = SandboxVerifier()

def _extract_agent_response(result: object) -> object:
    """
    Extract the structured response from a GeminiResult.

    Falls back to the supplied object for simple test doubles.
    """
    response = getattr(result, "response", None)

    if response is not None:
        return response

    return result

_remediation_state: dict[str, Any] = {
    "status": "idle",
    "result": None,
}

_rollback_state: dict[str, Any] = {
    "status": "idle",
    "result": None,
}


def scan_repository(
    repository_path: str,
) -> dict[str, Any]:
    """
    MCP-facing repository scan.

    This is a read-only adapter around the existing
    repository scanner. It does not modify repository files.
    """

    if not repository_path.strip():
        raise ValueError(
            "repository_path cannot be empty"
        )

    root = Path(repository_path).resolve()

    if not root.exists():
        raise FileNotFoundError(
            f"Repository root does not exist: {root}"
        )

    if not root.is_dir():
        raise ValueError(
            f"Repository path is not a directory: {root}"
        )

    scanned_files = repository_scan(root)

    return {
        "repository_path": str(root),
        "file_count": len(scanned_files),
        "files": [
            {
                "path": file.path,
                "language": file.language.value,
                "support_level": file.support_level.value,
                "size_bytes": file.size_bytes,
                "line_count": file.line_count,
            }
            for file in scanned_files
        ],
        "languages": {
            language.value: count
            for language, count in summarize_by_language(
                scanned_files
            ).items()
        },
    }


def get_incidents() -> dict[str, Any]:
    """
    Return all currently open self-healing incidents.
    """

    records = incident_manager.list_open()

    incidents = []

    for record in records:
        incident = record.incident

        incidents.append(
            {
                "fingerprint": incident_fingerprinter.fingerprint(
                    incident
                ),
                "status": record.status,
                "created_at": record.created_at,
                "source": incident.source,
                "code": incident.code,
                "message": incident.message,
                "file_path": incident.file_path,
                "line": incident.line,
                "column": incident.column,
            }
        )

    return {
        "count": len(incidents),
        "incidents": incidents,
    }


def inspect_incident(
    fingerprint: str,
) -> dict[str, Any]:
    """
    Inspect an open incident using its deterministic fingerprint.
    """

    if not fingerprint.strip():
        raise ValueError(
            "fingerprint cannot be empty"
        )

    records = incident_manager.list_open()

    for record in records:
        incident = record.incident

        current_fingerprint = (
            incident_fingerprinter.fingerprint(
                incident
            )
        )

        if current_fingerprint != fingerprint:
            continue

        return {
            "found": True,
            "fingerprint": current_fingerprint,
            "status": record.status,
            "created_at": record.created_at,
            "incident": {
                "source": incident.source,
                "code": incident.code,
                "message": incident.message,
                "file_path": incident.file_path,
                "line": incident.line,
                "column": incident.column,
            },
        }

    return {
        "found": False,
        "fingerprint": fingerprint,
        "error": "Incident not found",
    }

def diagnose_incident(
    fingerprint: str,
    repository_path: str,
) -> dict[str, Any]:
    """
    Build a deterministic diagnosis context for one open incident.

    This operation is read-only. It combines the incident
    with repository scope information for downstream repair.
    """

    if not fingerprint.strip():
        raise ValueError(
            "fingerprint cannot be empty"
        )

    if not repository_path.strip():
        raise ValueError(
            "repository_path cannot be empty"
        )

    incident_result = inspect_incident(
        fingerprint
    )

    if not incident_result["found"]:
        return {
            "found": False,
            "fingerprint": fingerprint,
            "error": "Incident not found",
        }

    incident = incident_result["incident"]
    file_path = incident["file_path"]

    if not file_path:
        return {
            "found": True,
            "fingerprint": fingerprint,
            "diagnosis": {
                "incident": incident,
                "scope": None,
                "reason": (
                    "Incident has no associated file path"
                ),
            },
        }

    scope = analyze_scope(
        repository_path,
        file_path,
        line=incident["line"],
    )

    return {
        "found": True,
        "fingerprint": fingerprint,
        "diagnosis": {
            "incident": incident,
            "scope": scope,
            "reason": (
                "Incident mapped to repository scope"
            ),
        },
    }

def survey_repository(
    repository_path: str,
    file_path: str,
) -> dict[str, Any]:
    """
    Inspect the target file and its local repository context.

    This is read-only. It prepares structured evidence for
    the repair generation stage.
    """

    if not repository_path.strip():
        raise ValueError(
            "repository_path cannot be empty"
        )

    if not file_path.strip():
        raise ValueError(
            "file_path cannot be empty"
        )

    scope = analyze_scope(
        repository_path,
        file_path,
    )

    return {
        "repository_path": repository_path,
        "file_path": file_path,
        "scope": scope,
        "survey": {
            "target_exists": True,
            "dependencies": scope["dependencies"],
            "related_tests": scope["related_tests"],
            "symbols": scope["symbols"],
            "imports": scope["imports"],
        },
    }

def generate_repair_candidate(
    repository_path: str,
    file_path: str,
    problem: str,
    confidence: float,
    patch: str | None = None,
) -> dict[str, Any]:
    """
    Generate a repair candidate using repository survey context.

    This operation is read-only. It never modifies repository files.
    """

    if not repository_path.strip():
        raise ValueError(
            "repository_path cannot be empty"
        )

    if not file_path.strip():
        raise ValueError(
            "file_path cannot be empty"
        )

    if not problem.strip():
        raise ValueError(
            "problem cannot be empty"
        )

    survey = survey_repository(
        repository_path,
        file_path,
    )

    candidate = generate_patch(
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        patch=patch,
    )

    return {
        "file_path": file_path,
        "problem": problem,
        "survey": survey["survey"],
        "candidate": candidate,
    }

def verify_repair_candidate(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """
    Verify a generated repair candidate through the
    existing deterministic patch validator.

    This operation does not modify repository files.
    """

    if not isinstance(candidate, dict):
        raise ValueError(
            "candidate must be a dictionary"
        )

    file_path = candidate.get("file_path", "")
    confidence = candidate.get("confidence")
    patch = candidate.get("patch")

    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError(
            "candidate file_path cannot be empty"
        )

    if not isinstance(confidence, (int, float)):
        raise ValueError(
            "candidate confidence must be numeric"
        )

    return verify_patch(
        file_path=file_path,
        confidence=float(confidence),
        patch=patch,
    )

def execute_repair_candidate(
    *,
    file_path: str,
    patch: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Execute a verified repair candidate through the existing
    deterministic patch executor.

    By default this performs a dry run and does not modify files.
    """

    if not file_path.strip():
        raise ValueError(
            "file_path cannot be empty"
        )

    if not patch.strip():
        raise ValueError(
            "patch cannot be empty"
        )

    applied = apply_patch(
        file_path=file_path,
        patch=patch,
        dry_run=dry_run,
    )

    return {
        "success": applied,
        "file_path": file_path,
        "dry_run": dry_run,
        "applied": applied,
    }

def review_repair_candidate(
    *,
    incident: str,
    surveyor_finding: str,
    proposed_patch: str,
    repository_context: str,
    structural_context: str = "",
) -> dict[str, Any]:
    """
    Run the existing adversarial reviewer against a repair
    candidate.

    The reviewer is advisory. It does not apply or approve
    the patch through the deterministic policy system.
    """

    if not incident.strip():
        raise ValueError(
            "incident cannot be empty"
        )

    if not surveyor_finding.strip():
        raise ValueError(
            "surveyor_finding cannot be empty"
        )

    if not proposed_patch.strip():
        raise ValueError(
            "proposed_patch cannot be empty"
        )

    if not repository_context.strip():
        raise ValueError(
            "repository_context cannot be empty"
        )

    config = SelfHealConfig()

    gemini = GeminiClient(config)

    reviewer = AdversarialReviewer(gemini)

    result = reviewer.review(
        incident=incident,
        surveyor_finding=surveyor_finding,
        proposed_patch=proposed_patch,
        repository_context=repository_context,
        structural_context=structural_context,
    )

    if not result.success:
        return {
            "success": False,
            "approved": False,
            "risk_level": None,
            "issues": [],
            "required_changes": [],
            "explanation": result.error,
            "confidence": None,
        }

    finding = result.response

    return {
        "success": True,
        "approved": finding.approved,
        "risk_level": finding.risk_level,
        "issues": finding.issues,
        "required_changes": finding.required_changes,
        "explanation": finding.explanation,
        "confidence": finding.confidence,
    }

def execute_approved_repair_candidate(
    *,
    file_path: str,
    patch: str,
    accepted: bool,
    policy_accepted: bool,
    verification_passed: bool,
    regression_passed: bool,
) -> dict[str, Any]:
    """
    Apply a repair only after all deterministic remediation
    gates have accepted the candidate.

    This is the execution boundary for approved repairs.
    """
    if not file_path.strip():
        return {
            "success": False,
            "executed": False,
            "error": "file_path cannot be empty.",
        }

    if not patch.strip():
        return {
            "success": False,
            "executed": False,
            "error": "patch cannot be empty.",
        }

    if not accepted:
        return {
            "success": False,
            "executed": False,
            "error": "Repair candidate was not accepted.",
        }

    if not policy_accepted:
        return {
            "success": False,
            "executed": False,
            "error": "Repair candidate failed policy.",
        }

    if not verification_passed:
        return {
            "success": False,
            "executed": False,
            "error": "Repair candidate failed verification.",
        }

    if not regression_passed:
        return {
            "success": False,
            "executed": False,
            "error": "Repair candidate failed regression checks.",
        }

    try:
        result = execute_repair_candidate(
            file_path=file_path,
            patch=patch,
            dry_run=False,
        )
    except (ValueError, RuntimeError) as exc:
        return {
            "success": False,
            "executed": False,
            "error": str(exc),
        }

    return {
        **result,
        "executed": result["success"],
    }

def run_agent_pipeline(
    *,
    incident: str,
    repository_context: str,
    structural_context: str = "",
) -> dict[str, Any]:
    """
    Run the AI diagnosis pipeline:

    Surveyor -> Coder -> Adversarial Reviewer.

    This operation is read-only. It does not apply patches,
    execute code, or make the deterministic policy decision.
    """

    if not incident.strip():
        raise ValueError(
            "incident cannot be empty"
        )

    if not repository_context.strip():
        raise ValueError(
            "repository_context cannot be empty"
        )

    config = SelfHealConfig.from_environment()
    gemini = GeminiClient(config)

    orchestrator = AgentOrchestrator(
        surveyor=SurveyorAgent(gemini),
        coder=CoderAgent(gemini),
        reviewer=AdversarialReviewer(gemini),
    )

    result = orchestrator.run(
        incident=incident,
        repository_context=repository_context,
        structural_context=structural_context,
    )

    survey_success = bool(
        getattr(result.survey, "success", False)
    )

    candidate_success = bool(
        getattr(result.candidate, "success", False)
    )

    review_success = bool(
        getattr(result.review, "success", False)
    )

    return {
        "success": (
            survey_success
            and candidate_success
            and review_success
        ),
        "survey": result.survey,
        "candidate": result.candidate,
        "review": result.review,
    }

def prepare_agent_repair_candidate(
    *,
    incident: str,
    repository_path: str,
    file_path: str,
    repository_context: str,
    structural_context: str = "",
    sandbox_command: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run the AI pipeline and deterministically validate
    the Coder's proposed patch.

    The patch is never applied by this function.
    """

    if not incident.strip():
        raise ValueError("incident cannot be empty")

    if not repository_path.strip():
        raise ValueError("repository_path cannot be empty")

    if not file_path.strip():
        raise ValueError("file_path cannot be empty")

    pipeline = run_agent_pipeline(
        incident=incident,
        repository_context=repository_context,
        structural_context=structural_context,
    )

    candidate_result = _extract_agent_response(
        pipeline["candidate"]
    )

    patch = getattr(candidate_result, "patch", None)
    confidence = getattr(candidate_result, "confidence", None)
    target_files = getattr(
        candidate_result,
        "target_files",
        [],
    )

    if not isinstance(patch, str) or not patch.strip():
        return {
            "success": False,
            "stage": "candidate_generation",
            "error": "Coder did not produce a patch.",
            "pipeline": pipeline,
        }

    if not isinstance(confidence, (int, float)):
        return {
            "success": False,
            "stage": "candidate_generation",
            "error": "Coder did not produce numeric confidence.",
            "pipeline": pipeline,
        }

    # Stage 1: deterministic patch validation.
    verification = verify_patch(
        file_path=file_path,
        confidence=float(confidence),
        patch=patch,
    )

    # Stage 2: optional isolated sandbox verification.
    sandbox_result = None

    if verification["valid"] and sandbox_command is not None:
        sandbox_result = verify_repair_in_sandbox(
            repository_path=repository_path,
            command=sandbox_command,
        )

    sandbox_passed = (
        sandbox_result is None
        or sandbox_result["passed"]
    )

    return {
        "success": (
            verification["valid"]
            and sandbox_passed
        ),
        "stage": "candidate_verification",
        "file_path": file_path,
        "patch": patch,
        "confidence": float(confidence),
        "target_files": target_files,
        "verification": verification,
        "sandbox": sandbox_result,
        "review": pipeline["review"],
    }

def evaluate_agent_repair_candidate(
    *,
    candidate: dict[str, Any],
    attempt: int,
    risk_level: str,
    auto_heal: bool,
    execution_passed: bool | None = None,
    regression_inputs: dict[str, Any] | None = None,
    sandbox_inputs: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Feed an AI-generated repair candidate into the existing
    deterministic remediation and policy pipeline.

    This function does not apply the patch.
    """

    if not isinstance(candidate, dict):
        raise ValueError("candidate must be a dictionary")

    if not candidate.get("success"):
        return {
            "accepted": False,
            "stage": "candidate_verification",
            "candidate": candidate,
            "execution_ready": False,
            "error": candidate.get(
                "error",
                "Repair candidate is not valid.",
            ),
        }

    verification_passed = bool(
        candidate.get("verification", {}).get(
            "valid",
            False,
        )
    )

    regression_passed = True

    result = run_remediation(
        attempt=attempt,
        verification_passed=verification_passed,
        regression_passed=regression_passed,
        risk_level=risk_level,
        auto_heal=auto_heal,
        execution_passed=execution_passed,
        error=error,
        regression_inputs=regression_inputs,
        sandbox_inputs=sandbox_inputs,
    )

    return {
        **result,
        "candidate": candidate,
        "execution_ready": (
            result["accepted"]
            and verification_passed
            and regression_passed
            and auto_heal
        ),
    }

def _resolve_local_dependencies(
    index: RepositoryIndex,
    file_path: str,
) -> list[dict[str, str]]:
    """
    Resolve locally indexed import modules to repository files.

    Resolution is intentionally conservative. Unresolved
    third-party or standard-library imports are omitted.
    """

    file_record = index.get_file(file_path)

    if file_record is None:
        return []

    module_to_path = {
    record.module: record.path
    for record in index.files.values()
    if record.module
    }

    dependencies: list[dict[str, str]] = []

    for import_record in file_record.imports:
        module = import_record.module

        if module in module_to_path:
            dependency = module_to_path[module]

            if dependency != file_path:
                dependencies.append(
    {
        "module": module,
        "file_path": dependency,
    }
)

    return sorted(
    dependencies,
    key=lambda item: item["file_path"],
)


def analyze_scope(
    repository_path: str,
    file_path: str,
    line: int | None = None,
) -> dict[str, Any]:
    """
    Analyze repository context around one file.

    The operation is read-only and combines the repository
    index with Python AST information when a source line is supplied.
    """

    if not repository_path.strip():
        raise ValueError(
            "repository_path cannot be empty"
        )

    if not file_path.strip():
        raise ValueError(
            "file_path cannot be empty"
        )

    if line is not None and line < 1:
        raise ValueError(
            "line must be greater than or equal to 1"
        )

    root = Path(repository_path).resolve()

    if not root.exists():
        raise FileNotFoundError(
            f"Repository root does not exist: {root}"
        )

    if not root.is_dir():
        raise ValueError(
            f"Repository path is not a directory: {root}"
        )

    index = RepositoryIndex(root)
    index.build()

    normalized_file_path = file_path.replace(
        "\\",
        "/",
    )

    record = index.get_file(
        normalized_file_path
    )

    if record is None:
        raise FileNotFoundError(
            f"File is not indexed: {file_path}"
        )

    result: dict[str, Any] = {
        "repository_path": str(root),
        "file_path": record.path,
        "language": record.language,
        "module": record.module,
        "lines": record.lines,
        "parse_error": record.parse_error,
        "symbols": [
            {
                "name": symbol.name,
                "qualified_name": symbol.qualified_name,
                "kind": symbol.kind,
                "line": symbol.line,
                "end_line": symbol.end_line,
                "parent": symbol.parent,
            }
            for symbol in record.symbols
        ],
        "imports": [
            {
                "module": item.module,
                "name": item.name,
                "alias": item.alias,
                "line": item.line,
            }
            for item in record.imports
        ],
        "references": [
            {
                "name": item.name,
                "line": item.line,
                "context": item.context,
            }
            for item in record.references
        ],
        "related_tests": index.related_tests(
            normalized_file_path
        ),
        "dependencies": _resolve_local_dependencies(
            index,
            normalized_file_path,
        ),
    }

    if line is not None:
        source_path = root / Path(
            normalized_file_path
        )

        if not source_path.exists():
            raise FileNotFoundError(
                f"File does not exist: {file_path}"
            )

        source = source_path.read_text(
            encoding="utf-8"
        )

        source_lines = source.splitlines()

        if line > len(source_lines):
            raise ValueError(
                f"line {line} is outside the file"
            )

        analyzer = PythonASTAnalyzer()
        tree = analyzer.parse_source(source)

        location = analyzer.locate(
            tree,
            line,
        )

        scope = analyzer.scope_at(
            tree,
            line,
        )

        result["ast"] = {
            "available": True,
            "location": (
                {
                    "node_type": location.node_type,
                    "name": location.name,
                    "line_start": location.line_start,
                    "line_end": location.line_end,
                    "column_start": location.column_start,
                    "column_end": location.column_end,
                }
                if location is not None
                else None
            ),
            "scope": (
                {
                    "module": scope.module,
                    "classes": list(scope.classes),
                    "functions": list(scope.functions),
                }
                if scope is not None
                else None
            ),
            "source_segment": (
                analyzer.source_segment(
                    source,
                    tree,
                    line,
                )
            ),
        }

    return result


def generate_patch(
    file_path: str,
    problem: str,
    confidence: float,
    patch: str | None = None,
) -> dict[str, Any]:
    """
    Generate a structured repair candidate.

    This operation only creates a candidate. It never
    modifies repository files.
    """

    if not file_path.strip():
        raise ValueError(
            "file_path cannot be empty"
        )

    if not problem.strip():
        raise ValueError(
            "problem cannot be empty"
        )
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
        "confidence must be between 0.0 and 1.0"
    )

    candidate = generate_candidate(
        file_path=file_path,
        problem=problem,
        confidence=confidence,
        patch=patch,
    )

    return {
        "file_path": candidate.file_path,
        "description": candidate.description,
        "confidence": candidate.confidence,
        "patch": candidate.patch,
    }


def verify_patch(
    file_path: str,
    confidence: float,
    patch: str | None = None,
) -> dict[str, Any]:
    """
    Verify a proposed repair candidate without applying it.

    The existing deterministic validator is the authority
    for patch structure and candidate validity.
    """

    if not file_path.strip():
        raise ValueError(
            "file_path cannot be empty"
        )

    validation = validate_candidate(
        file_path=file_path,
        confidence=confidence,
        patch=patch,
    )

    return {
        "valid": validation.valid,
        "errors": validation.errors,
        "file_path": file_path,
        "confidence": confidence,
        "patch_provided": patch is not None,
    }

def _serialize_attempt(
    attempt: RemediationAttemptResult,
) -> dict[str, Any]:
    """
    Convert one controller attempt into an MCP-safe dictionary.
    """

    return {
        "attempt": attempt.attempt,
        "verification_passed": (
            attempt.verification_passed
        ),
        "regression_passed": (
            attempt.regression_passed
        ),
        "error": attempt.error,
        "policy": {
            "accepted": attempt.policy.accepted,
            "requires_human_review": (
                attempt.policy.requires_human_review
            ),
            "reason": attempt.policy.reason,
        },
    }

def run_regression_gate(
    *,
    baseline_checks: list[dict[str, Any]],
    candidate_checks: list[dict[str, Any]],
    baseline_files: list[dict[str, Any]],
    candidate_files: list[dict[str, Any]],
    approved_files: list[str],
) -> dict[str, Any]:
    """
    Run the deterministic regression gate.

    This compares baseline and candidate verification results
    and ensures that only approved repository files changed.
    """

    def make_check(
        item: dict[str, Any],
    ) -> CheckResult:
        return CheckResult(
            name=str(item["name"]),
            passed=bool(item["passed"]),
            return_code=int(item["return_code"]),
            stdout=str(item.get("stdout", "")),
            stderr=str(item.get("stderr", "")),
        )

    def make_snapshot(
        item: dict[str, Any],
    ) -> FileSnapshot:
        return FileSnapshot(
            path=str(item["path"]),
            content=str(item["content"]),
        )

    baseline_check_objects = [
        make_check(item)
        for item in baseline_checks
    ]

    candidate_check_objects = [
        make_check(item)
        for item in candidate_checks
    ]

    baseline_file_objects = [
        make_snapshot(item)
        for item in baseline_files
    ]

    candidate_file_objects = [
        make_snapshot(item)
        for item in candidate_files
    ]

    result = evaluate_regression(
        baseline_checks=baseline_check_objects,
        candidate_checks=candidate_check_objects,
        baseline_files=baseline_file_objects,
        candidate_files=candidate_file_objects,
        approved_files=set(approved_files),
    )

    return {
        "passed": result.passed,
        "reasons": list(result.reasons),
        "verification": {
            "passed": result.verification.passed,
            "regressions": list(
                result.verification.regressions
            ),
        },
        "scope": {
            "passed": result.scope.passed,
            "changed_files": list(
                result.scope.changed_files
            ),
            "unexpected_files": list(
                result.scope.unexpected_files
            ),
        },
    }

def run_remediation(
    *,
    attempt: int,
    verification_passed: bool,
    regression_passed: bool,
    risk_level: str,
    auto_heal: bool,
    execution_passed: bool | None = None,
    error: str | None = None,
    regression_inputs: dict[str, Any] | None = None,
    sandbox_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate one remediation attempt through the existing
    deterministic remediation controller.

    This MCP tool does not generate or apply patches.
    It evaluates verification, regression, risk, and policy.
    """

    if attempt < 1:
        raise ValueError(
            "attempt must be greater than or equal to 1"
        )

    if not risk_level.strip():
        raise ValueError(
            "risk_level cannot be empty"
        )

    try:
        normalized_risk = RiskLevel(
            risk_level.upper()
        )
    except ValueError as exc:
        valid_levels = ", ".join(
            level.value
            for level in RiskLevel
        )

        raise ValueError(
            "Invalid risk_level. Expected one of: "
            f"{valid_levels}"
        ) from exc

    if regression_inputs is not None:
        regression_result = run_regression_gate(
            baseline_checks=regression_inputs.get(
                "baseline_checks",
                [],
            ),
            candidate_checks=regression_inputs.get(
                "candidate_checks",
                [],
            ),
            baseline_files=regression_inputs.get(
                "baseline_files",
                [],
            ),
            candidate_files=regression_inputs.get(
                "candidate_files",
                [],
            ),
            approved_files=regression_inputs.get(
                "approved_files",
                [],
            ),
        )

        regression_passed = regression_result["passed"]

        if not regression_passed:
            regression_reasons = regression_result["reasons"]

            if regression_reasons:
                error = (
                    f"{error}; "
                    if error
                    else ""
                ) + "; ".join(
                    regression_reasons
                )

    if sandbox_inputs is not None:
        sandbox_result = verify_repair_in_sandbox(
            repository_path=sandbox_inputs.get(
                "repository_path",
                "",
            ),
            command=sandbox_inputs.get(
                "command",
                [],
            ),
        )

        verification_passed = (
            verification_passed
            and sandbox_result["passed"]
        )

        if not sandbox_result["passed"]:
            sandbox_error = (
                sandbox_result["stderr"]
                or sandbox_result["stdout"]
            )

            error = (
                f"{error}; "
                if error
                else ""
            ) + "Sandbox verification failed"

            if sandbox_error:
                error += f": {sandbox_error}"
    
    attempt_result = remediation_controller.create_attempt(
        attempt=attempt,
        verification_passed=(
            verification_passed
            and (
                execution_passed
                if execution_passed is not None
                else True
            )
        ),
        regression_passed=regression_passed,
        risk_level=normalized_risk,
        auto_heal=auto_heal,
        error=error,
    )

    

    controller_result = (
        remediation_controller.evaluate(
            attempts=[attempt_result],
            risk_level=normalized_risk,
            auto_heal=auto_heal,
        )
    )

    exhausted = (
        controller_result.exhausted
        or (
            attempt >= 3
            and not attempt_result.verification_passed
        )
    )

    result = {
        "status": (
            "accepted"
            if controller_result.accepted
            else (
                "human_review_required"
                if controller_result.requires_human_review
                else (
                    "exhausted"
                    if controller_result.exhausted
                    else "rejected"
                )
            )
        ),
        "accepted": controller_result.accepted,
        "requires_human_review": (
            controller_result.requires_human_review
        ),
        "policy": {
            "accepted": controller_result.accepted,
            "requires_human_review": (
                controller_result.requires_human_review
            ),
        },
        "exhausted": exhausted,

        "attempts": [
            _serialize_attempt(item)
            for item in controller_result.attempts
        ],
    }

    _remediation_state["status"] = result["status"]
    _remediation_state["result"] = result

    return result


def get_remediation_status() -> dict[str, Any]:
    """
    Return the latest MCP remediation evaluation state.

    This operation is read-only.
    """

    result = _remediation_state["result"]

    if result is None:
        return {
            "status": "idle",
            "result": None,
        }

    return {
        "status": _remediation_state["status"],
        "result": result,
    }


def rollback(
    *,
    verification_passed: bool,
    regression_passed: bool,
    retry_exhausted: bool,
    policy_accepted: bool,
) -> dict[str, Any]:
    """
    Determine whether a remediation candidate must be rolled back.

    This tool only makes the deterministic rollback decision.
    It does NOT execute Git reset, restore, or other filesystem
    operations.
    """

    decision = rollback_controller.evaluate(
        verification_passed=verification_passed,
        regression_passed=regression_passed,
        retry_exhausted=retry_exhausted,
        policy_accepted=policy_accepted,
    )

    result = {
        "rollback_required": decision.required,
        "reason": (
            decision.reason.value
            if decision.reason is not None
            else None
        ),
    }

    _rollback_state["status"] = (
        "rollback_required"
        if decision.required
        else "no_rollback_required"
    )
    _rollback_state["result"] = result

    return result

def verify_repair_in_sandbox(
    repository_path: str,
    command: list[str],
) -> dict[str, Any]:
    """
    Verify a repair candidate inside an isolated sandbox.

    The original repository is never modified.
    """
    if not repository_path.strip():
        raise ValueError("repository_path cannot be empty")

    if not command:
        raise ValueError("command cannot be empty")

    result = sandbox_verifier.verify(
        repository_path=repository_path,
        command=command,
    )

    return {
        "passed": result.passed,
        "return_code": result.sandbox_result.return_code,
        "stdout": result.sandbox_result.stdout,
        "stderr": result.sandbox_result.stderr,
        "timed_out": result.sandbox_result.timed_out,
        "command": list(result.command),
    }