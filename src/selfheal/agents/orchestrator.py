from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentPipelineResult:
    survey: object
    candidate: object
    review: object


def _result_text(result: object) -> str:
    """
    Extract useful textual content from an agent result.

    GeminiResult exposes its generated content through `text`.
    The fallback keeps the orchestrator compatible with simple
    test doubles.
    """
    text = getattr(result, "text", None)

    if isinstance(text, str) and text.strip():
        return text

    return str(result)


class AgentOrchestrator:
    """
    Coordinates Surveyor -> Coder -> Adversarial Reviewer.

    AI agents only produce analysis and proposals.
    Deterministic verification, regression, and policy
    decisions remain outside the AI pipeline.
    """

    def __init__(
        self,
        surveyor,
        coder,
        reviewer,
    ):
        self.surveyor = surveyor
        self.coder = coder
        self.reviewer = reviewer

    def run(
        self,
        *,
        incident: str,
        repository_context: str,
        structural_context: str = "",
    ) -> AgentPipelineResult:
        survey_result = self.surveyor.analyze(
            incident=incident,
            repository_context=repository_context,
            structural_context=structural_context,
        )

        candidate_result = self.coder.generate_patch(
            incident=incident,
            surveyor_finding=_result_text(survey_result),
            repository_context=repository_context,
            structural_context=structural_context,
        )

        review_result = self.reviewer.review(
            incident=incident,
            surveyor_finding=_result_text(survey_result),
            proposed_patch=_result_text(candidate_result),
            repository_context=repository_context,
            structural_context=structural_context,
        )

        return AgentPipelineResult(
            survey=survey_result,
            candidate=candidate_result,
            review=review_result,
        )