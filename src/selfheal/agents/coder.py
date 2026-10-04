from __future__ import annotations

from pydantic import BaseModel, Field

from selfheal.agents.gemini import GeminiClient, GeminiResult
from selfheal.security.scrubber import scrub_secrets


class CoderPatch(BaseModel):
    """Structured patch proposal returned by the Coder agent."""

    summary: str
    patch: str
    target_files: list[str] = Field(default_factory=list)
    explanation: str
    confidence: float


class CoderAgent:
    """
    Read-only AI coding agent.

    The Coder proposes a unified diff only.
    It never writes or modifies repository files.
    """

    def __init__(self, gemini: GeminiClient):
        self.gemini = gemini

    def generate_patch(
        self,
        incident: str,
        surveyor_finding: str,
        repository_context: str,
        structural_context: str = "",
    ) -> GeminiResult:
        """
        Generate a structured unified-diff proposal.

        Repository context is scrubbed before submission.
        """

        safe_incident = scrub_secrets(incident)
        safe_finding = scrub_secrets(surveyor_finding)
        safe_repository_context = scrub_secrets(repository_context)
        safe_structural_context = scrub_secrets(structural_context)

        prompt = f"""
You are the Coder agent in a self-healing CI/CD system.

Your role is to PROPOSE a minimal source-code repair.

STRICT RULES:
- Do not rewrite entire files.
- Do not invent files.
- Do not modify files directly.
- Return ONLY a unified diff in the patch field.
- The patch must target only files supported by the supplied context.
- Keep the change as small as possible.
- Do not include secrets.
- Do not include markdown fences around the unified diff.
- Do not claim the patch was applied or tested.

Incident:
{safe_incident}

Surveyor finding:
{safe_finding}

Repository context:
{safe_repository_context}

Structural context:
{safe_structural_context}

Return structured JSON matching the requested schema.
"""

        return self.gemini.generate_json(
            prompt,
            response_schema=CoderPatch,
        )