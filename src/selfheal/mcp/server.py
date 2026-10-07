from __future__ import annotations

import functools

from mcp.server.fastmcp import FastMCP

from selfheal.security.paths import ensure_allowed

from selfheal.mcp.tools import (
    run_integrated_remediation,
    diagnose_incident,
    analyze_scope,
    generate_patch,
    get_incidents,
    get_remediation_status,
    inspect_incident,
    review_repair_candidate,
    rollback,
    run_remediation,
    scan_repository,
    verify_patch,
    run_regression_gate,
    verify_repair_in_sandbox,
    run_agent_pipeline,
    prepare_agent_repair_candidate,
    evaluate_agent_repair_candidate,
    execute_approved_repair_candidate,

)


def _guarded(fn):
    """Reject path arguments outside SELFHEAL_ALLOWED_ROOTS (default: cwd)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        for key in ("repository_path", "file_path", "project_path"):
            if kwargs.get(key):
                ensure_allowed(kwargs[key])
        nested = kwargs.get("sandbox_inputs")
        if isinstance(nested, dict) and nested.get("repository_path"):
            ensure_allowed(nested["repository_path"])
        return fn(*args, **kwargs)

    return wrapper


def create_mcp_server() -> FastMCP:
    """
    Create the Self-Healing MCP server.
    """

    server = FastMCP(
        name="self-healing-engine"
    )

    server.tool(
        name="scan_repository",
        description=(
            "Scan a repository and return deterministic "
            "file and language metadata."
        ),
    )(_guarded(scan_repository))

    server.tool(
        name="get_incidents",
        description=(
            "Return all currently open "
            "self-healing incidents."
        ),
    )(_guarded(get_incidents))

    server.tool(
        name="inspect_incident",
        description=(
            "Inspect an open incident using "
            "its deterministic fingerprint."
        ),
    )(_guarded(inspect_incident))

    server.tool(
        name="analyze_scope",
        description=(
            "Analyze repository structure, dependencies, "
            "symbols, references, tests, and optional "
            "Python AST context for a target file."
        ),
    )(_guarded(analyze_scope))

    server.tool(
        name="generate_patch",
        description=(
            "Generate a structured repair candidate "
            "without modifying repository files."
        ),
    )(_guarded(generate_patch))

    server.tool(
        name="verify_patch",
        description=(
            "Deterministically validate a proposed "
            "repair patch without applying it."
        ),
    )(_guarded(verify_patch))

    server.tool(
        name="review_repair_candidate",
        description=(
            "Run the adversarial reviewer against a proposed "
            "repair candidate. Reviewer approval is advisory; "
            "deterministic policy remains authoritative."
        ),
    )(_guarded(review_repair_candidate))

    server.tool(
        name="run_remediation",
        description=(
            "Evaluate a remediation attempt through the "
            "deterministic verification, regression, "
            "risk, retry, and policy controls."
        ),
    )(_guarded(run_remediation))

    server.tool(
        name="get_remediation_status",
        description=(
            "Return the latest remediation evaluation "
            "state."
        ),
    )(_guarded(get_remediation_status))

    server.tool(
        name="rollback",
        description=(
            "Determine whether a remediation candidate "
            "must be rolled back based on verification, "
            "regression, retry, and policy results."
        ),
    )(_guarded(rollback))

    server.tool(
            name="run_regression_gate",
            description=(
                "Run deterministic verification and file-scope "
                "regression checks for a repair candidate."
            ),
        )(_guarded(run_regression_gate))

    server.tool(
            name="verify_repair_in_sandbox",
            description=(
                "Verify a repair candidate inside an isolated "
                "sandbox without modifying the source repository."
        ),
    )(_guarded(verify_repair_in_sandbox))

    server.tool(
        name="run_agent_pipeline",
        description=(
            "Run the Surveyor, Coder, and Adversarial Reviewer "
            "pipeline for a repair candidate. This operation "
            "is read-only and does not apply patches."
        ),
    )(_guarded(run_agent_pipeline))

    server.tool(
        name="prepare_agent_repair_candidate",
        description=(
            "Run the Surveyor, Coder, and Reviewer pipeline, "
            "then deterministically validate the generated "
            "repair candidate without applying it."
        ),
    )(_guarded(prepare_agent_repair_candidate))

    server.tool(
        name="evaluate_agent_repair_candidate",
        description=(
            "Feed a validated AI repair candidate into the "
            "deterministic regression, policy, and remediation "
            "pipeline without applying the patch."
        ),
    )(_guarded(evaluate_agent_repair_candidate))

    server.tool(
        name="execute_approved_repair_candidate",
        description=(
            "Apply a repair candidate only after deterministic "
            "verification, regression, and policy gates have accepted it."
        ),
    )(_guarded(execute_approved_repair_candidate))

    server.tool(
        name="diagnose_incident",
        description=(
            "Build a read-only diagnosis context (incident plus "
            "repository scope) for one open incident fingerprint."
        ),
    )(_guarded(diagnose_incident))

    server.tool(
        name="run_integrated_remediation",
        description=(
            "Run the full SelfHeal engine workflow for a CI failure log: "
            "diagnosis, AI/rule-based candidate, validation, risk/policy, "
            "sandbox, regression, optional transactional execution. "
            "Mutating options require SELFHEAL_MCP_ALLOW_APPLY=true."
        ),
    )(_guarded(run_integrated_remediation))

    return server




mcp_server = create_mcp_server()