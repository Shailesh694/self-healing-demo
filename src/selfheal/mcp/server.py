from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from selfheal.mcp.tools import (
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
    execute_repair_candidate,
    run_regression_gate,
    verify_repair_in_sandbox,
    run_agent_pipeline,
    prepare_agent_repair_candidate,
    evaluate_agent_repair_candidate,
    execute_approved_repair_candidate,

)


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
    )(scan_repository)

    server.tool(
        name="get_incidents",
        description=(
            "Return all currently open "
            "self-healing incidents."
        ),
    )(get_incidents)

    server.tool(
        name="inspect_incident",
        description=(
            "Inspect an open incident using "
            "its deterministic fingerprint."
        ),
    )(inspect_incident)

    server.tool(
        name="analyze_scope",
        description=(
            "Analyze repository structure, dependencies, "
            "symbols, references, tests, and optional "
            "Python AST context for a target file."
        ),
    )(analyze_scope)

    server.tool(
        name="generate_patch",
        description=(
            "Generate a structured repair candidate "
            "without modifying repository files."
        ),
    )(generate_patch)

    server.tool(
        name="verify_patch",
        description=(
            "Deterministically validate a proposed "
            "repair patch without applying it."
        ),
    )(verify_patch)

    server.tool(
        name="review_repair_candidate",
        description=(
            "Run the adversarial reviewer against a proposed "
            "repair candidate. Reviewer approval is advisory; "
            "deterministic policy remains authoritative."
        ),
    )(review_repair_candidate)

    server.tool(
        name="run_remediation",
        description=(
            "Evaluate a remediation attempt through the "
            "deterministic verification, regression, "
            "risk, retry, and policy controls."
        ),
    )(run_remediation)

    server.tool(
        name="get_remediation_status",
        description=(
            "Return the latest remediation evaluation "
            "state."
        ),
    )(get_remediation_status)

    server.tool(
        name="rollback",
        description=(
            "Determine whether a remediation candidate "
            "must be rolled back based on verification, "
            "regression, retry, and policy results."
        ),
    )(rollback)

    server.tool(
    name="execute_repair_candidate",
    description=(
        "Execute a verified repair candidate through "
        "the deterministic patch executor."
        ),
    )(execute_repair_candidate)

    server.tool(
            name="run_regression_gate",
            description=(
                "Run deterministic verification and file-scope "
                "regression checks for a repair candidate."
            ),
        )(run_regression_gate)

    server.tool(
            name="verify_repair_in_sandbox",
            description=(
                "Verify a repair candidate inside an isolated "
                "sandbox without modifying the source repository."
        ),
    )(verify_repair_in_sandbox)

    server.tool(
        name="run_agent_pipeline",
        description=(
            "Run the Surveyor, Coder, and Adversarial Reviewer "
            "pipeline for a repair candidate. This operation "
            "is read-only and does not apply patches."
        ),
    )(run_agent_pipeline)

    server.tool(
        name="prepare_agent_repair_candidate",
        description=(
            "Run the Surveyor, Coder, and Reviewer pipeline, "
            "then deterministically validate the generated "
            "repair candidate without applying it."
        ),
    )(prepare_agent_repair_candidate)

    server.tool(
        name="prepare_agent_repair_candidate",
        description=(
            "Run the Surveyor, Coder, and Reviewer pipeline, "
            "then deterministically validate the repair candidate "
            "without applying it."
        ),
    )(prepare_agent_repair_candidate)

    server.tool(
        name="evaluate_agent_repair_candidate",
        description=(
            "Feed a validated AI repair candidate into the "
            "deterministic regression, policy, and remediation "
            "pipeline without applying the patch."
        ),
    )(evaluate_agent_repair_candidate)

    server.tool(
        name="execute_approved_repair_candidate",
        description=(
            "Apply a repair candidate only after deterministic "
            "verification, regression, and policy gates have accepted it."
        ),
    )(execute_approved_repair_candidate)

    return server




mcp_server = create_mcp_server()