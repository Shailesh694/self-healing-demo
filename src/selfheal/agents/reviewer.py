from __future__ import annotations

from pydantic import BaseModel, Field

from selfheal.agents.gemini import GeminiClient, GeminiResult
from selfheal.security.scrubber import scrub_secrets


class ReviewFinding(BaseModel):
    """Structured adversarial review returned by the reviewer agent."""

    approved: bool
    risk_level: str
    issues: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    explanation: str
    confidence: float


class AdversarialReviewer:
    """
    Adversarial review agent.

    The reviewer challenges a proposed patch.
    It cannot modify, apply, or approve a patch outside
    the deterministic policy system.
    """

    def __init__(self, gemini: GeminiClient):
        self.gemini = gemini

    def review(
        self,
        incident: str,
        surveyor_finding: str,
        proposed_patch: str,
        repository_context: str,
        structural_context: str = "",
    ) -> GeminiResult:
        """
        Critically review a proposed patch.

        The reviewer receives only scoped and scrubbed context.
        """

        safe_incident = scrub_secrets(incident)
        safe_finding = scrub_secrets(surveyor_finding)
        safe_patch = scrub_secrets(proposed_patch)
        safe_repository_context = scrub_secrets(repository_context)
        safe_structural_context = scrub_secrets(structural_context)

        prompt = f"""
You are the Adversarial Reviewer in a self-healing CI/CD system.

Your job is to actively challenge the proposed repair.

Do not modify files.
Do not apply the patch.
Do not assume the patch is correct because the Coder proposed it.

Look for:
- incorrect root-cause assumptions
- unrelated file changes
- excessive scope
- security problems
- regressions
- broken edge cases
- missing tests
- API or behavior changes
- syntactically invalid patches
- changes that do not actually address the incident

Incident:
{safe_incident}

Surveyor finding:
{safe_finding}

Proposed unified diff:
{safe_patch}

Repository context:
{safe_repository_context}

Structural context:
{safe_structural_context}

Return structured JSON matching the requested schema.

Use approved=true only when there are no material concerns.
Use risk_level as one of:
LOW, MEDIUM, HIGH, CRITICAL.

Do not treat your approval as the final policy decision.
"""

        return self.gemini.generate_json(
            prompt,
            response_schema=ReviewFinding,
        )