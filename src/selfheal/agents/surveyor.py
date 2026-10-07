from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from selfheal.agents.gemini import GeminiClient, GeminiResult
from selfheal.security.scrubber import scrub_secrets


class SurveyorFinding(BaseModel):
    """Structured finding produced by the Surveyor agent."""

    root_cause: str
    affected_files: list[str] = Field(default_factory=list)
    affected_symbols: list[str] = Field(default_factory=list)
    relevant_tests: list[str] = Field(default_factory=list)
    explanation: str
    confidence: float


class SurveyorAgent:
    """
    Read-only repository analysis agent.

    The Surveyor may inspect supplied context but cannot modify
    repository files or generate/apply patches.
    """

    def __init__(self, gemini: GeminiClient):
        self.gemini = gemini

    def analyze(
        self,
        incident: str,
        repository_context: str,
        structural_context: str = "",
    ) -> GeminiResult:
        """
        Analyze a scoped incident and return a structured finding.

        Context is scrubbed before being submitted to Gemini.
        """

        safe_incident = scrub_secrets(incident)
        safe_repository_context = scrub_secrets(repository_context)
        safe_structural_context = scrub_secrets(structural_context)

        prompt = f"""
You are the Surveyor agent in a self-healing CI/CD system.

Your role is READ-ONLY diagnosis.

Do not propose a patch.
Do not rewrite files.
Do not invent repository facts.
Use only the supplied incident and scoped repository context.

Incident:
{safe_incident}

Repository context:
{safe_repository_context}

Structural context:
{safe_structural_context}

Return JSON matching the requested schema.

Identify:
- likely root cause
- affected files
- affected symbols
- relevant tests
- concise explanation
- confidence between 0 and 1
"""

        return self.gemini.generate_json(
            prompt,
            response_schema=SurveyorFinding,
        )