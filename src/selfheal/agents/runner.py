"""
Engine-layer AI runner: Surveyor -> Coder -> Adversarial Reviewer.

The AI only proposes. This module never applies anything; the engine's
deterministic gates decide whether a proposal is used.
"""
from __future__ import annotations

from typing import Any

from selfheal.agents.coder import CoderAgent
from selfheal.agents.gemini import GeminiClient
from selfheal.agents.orchestrator import AgentOrchestrator
from selfheal.agents.reviewer import AdversarialReviewer
from selfheal.agents.surveyor import SurveyorAgent
from selfheal.analysis.validator import validate_candidate
from selfheal.config import SelfHealConfig


def ai_available() -> bool:
    config = SelfHealConfig.from_environment()
    return bool(config.gemini_enabled and config.gemini_api_key)


def prepare_candidate(
    *,
    incident: str,
    repository_path: str,
    file_path: str,
    repository_context: str,
    structural_context: str = "",
) -> dict[str, Any]:
    config = SelfHealConfig.from_environment()
    gemini = GeminiClient(config)
    result = AgentOrchestrator(
        surveyor=SurveyorAgent(gemini),
        coder=CoderAgent(gemini),
        reviewer=AdversarialReviewer(gemini),
    ).run(
        incident=incident,
        repository_context=repository_context,
        structural_context=structural_context,
    )

    for name in ("survey", "candidate", "review"):
        part = getattr(result, name, None)
        if not getattr(part, "success", False):
            return {
                "success": False,
                "stage": name,
                "error": getattr(part, "error", None) or f"{name} stage failed",
            }

    proposal = getattr(result.candidate, "response", result.candidate)
    patch = getattr(proposal, "patch", None)
    confidence = getattr(proposal, "confidence", None)
    if not isinstance(patch, str) or not patch.strip():
        return {"success": False, "stage": "candidate", "error": "Coder produced no patch"}
    if not isinstance(confidence, (int, float)):
        return {"success": False, "stage": "candidate", "error": "Coder produced no confidence"}

    verdict = validate_candidate(
        file_path=file_path, confidence=float(confidence), patch=patch
    )
    return {
        "success": bool(verdict.valid),
        "patch": patch,
        "confidence": float(confidence),
        "review": result.review,
        "verification": {"valid": verdict.valid, "errors": list(verdict.errors)},
        "error": None if verdict.valid else "; ".join(verdict.errors),
    }
