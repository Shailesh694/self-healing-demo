from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CIResult:
    provider: str
    success: bool
    branch: str
    commit: str
    logs: str


def parse_ci_result(
    payload: dict,
    *,
    provider: str = "generic",
) -> CIResult:
    """
    Normalize a CI result into a common format.
    """

    return CIResult(
        provider=provider,
        success=bool(payload.get("success", False)),
        branch=str(payload.get("branch", "")),
        commit=str(payload.get("commit", "")),
        logs=str(payload.get("logs", "")),
    )


def normalize_github_payload(payload: dict) -> dict:
    """
    Convert a GitHub ``workflow_run`` webhook into the generic payload shape.

    GitHub does not send logs in the webhook; callers may add a ``logs`` field
    (for example from a workflow step). Extra keys are preserved.
    """
    run = payload.get("workflow_run")
    out = dict(payload)
    if not isinstance(run, dict):
        return out
    out["success"] = run.get("conclusion") == "success"
    out.setdefault("branch", run.get("head_branch", ""))
    out.setdefault("commit", run.get("head_sha", ""))
    if not out.get("logs"):
        out["logs"] = (
            f"GitHub workflow '{run.get('name', '')}' "
            f"concluded {run.get('conclusion')}"
        )
    if run.get("id") and not out.get("incident_id"):
        out["incident_id"] = f"gh-{run['id']}"
    return out
