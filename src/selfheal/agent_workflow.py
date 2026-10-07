"""
AI repair path for the webhook workflow.

Surveyor -> Coder -> Adversarial Reviewer -> deterministic verification.
The AI only *proposes*; nothing is applied unless the reviewer approves AND
deterministic verification accepts the patch. Application, tests, Git and
rollback are then handled by repair_and_verify().
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .logger import get_logger

MAX_CONTEXT_CHARS = 20_000
MIN_AI_CONFIDENCE = 0.7

log = get_logger("selfheal.agents")


def build_repository_context(file_path: str, project_path: str) -> tuple[str, str]:
    """Return (repository_context, structural_context) for the target file."""
    source = Path(file_path).read_text(encoding="utf-8")[:MAX_CONTEXT_CHARS]
    numbered = "\n".join(
        f"{i}: {line}" for i, line in enumerate(source.splitlines(), 1)
    )
    context = f"FILE {file_path}\n{numbered}"

    structural = ""
    try:
        from .repository.index import RepositoryIndex

        index = RepositoryIndex(project_path).build()
        tests = index.related_tests(file_path)
        imports = [
            getattr(i, "module", str(i))
            for i in index.imports_for(file_path)
        ]
        structural = (
            f"index summary: {index.summary()}\n"
            f"related tests: {tests}\n"
            f"imports (dependencies) of target: {imports}"
        )
    except Exception:  # context enrichment is best-effort only
        pass
    return context, structural


def propose_ai_patch(
    *,
    incident: str,
    file_path: str,
    project_path: str,
    prepare: Callable[..., dict] | None = None,
) -> dict:
    """
    Run the agent pipeline and gate its proposal.

    Returns {"approved": bool, "reason": str, "patch": str|None, "confidence",
    "review", "verification"}. `prepare` is injectable for tests.
    """
    if prepare is None:
        from .agents.runner import prepare_candidate as prepare

    context, structural = build_repository_context(file_path, project_path)
    try:
        prepared = prepare(
            incident=incident,
            repository_path=project_path,
            file_path=file_path,
            repository_context=context,
            structural_context=structural,
        )
    except Exception as exc:  # no API key, network, schema errors ...
        return {"approved": False, "reason": f"agent pipeline failed: {exc}", "patch": None}

    if not prepared.get("success"):
        return {
            "approved": False,
            "reason": prepared.get("error") or "deterministic verification rejected the AI patch",
            "patch": None,
            "verification": prepared.get("verification"),
        }

    review = getattr(prepared.get("review"), "response", prepared.get("review"))
    approved = bool(getattr(review, "approved", False))
    risk_level = str(getattr(review, "risk_level", "high")).lower()
    if not approved or risk_level in {"high", "critical"}:
        return {
            "approved": False,
            "reason": f"adversarial reviewer did not approve (risk={risk_level})",
            "patch": None,
            "review": review,
        }

    if float(prepared["confidence"]) < MIN_AI_CONFIDENCE:
        return {
            "approved": False,
            "reason": (
                f"AI confidence {prepared['confidence']} below "
                f"minimum {MIN_AI_CONFIDENCE}"
            ),
            "patch": None,
        }

    log.info("AI patch approved for %s", file_path)
    return {
        "approved": True,
        "reason": "reviewer approved; deterministic verification passed",
        "patch": prepared["patch"],
        "confidence": prepared["confidence"],
        "review": review,
        "verification": prepared.get("verification"),
    }
