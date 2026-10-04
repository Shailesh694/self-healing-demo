from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from google import genai
from pydantic import BaseModel, Field, ValidationError

from selfheal.config import SelfHealConfig


class GeminiResponse(BaseModel):
    """Default structured response model."""

    response_type: str
    summary: str
    confidence: float
    data: list[str] = Field(default_factory=list)


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


@dataclass(frozen=True)
class GeminiResult:
    """Safe wrapper around a Gemini request."""

    success: bool
    response: BaseModel | None = None
    error: str | None = None


class GeminiClient:
    """
    Structured Gemini client.

    Gemini is allowed to propose information only.
    This client never writes repository files.
    """

    def __init__(self, config: SelfHealConfig):
        self.config = config

        if not config.gemini_api_key:
            self._client = None
            return

        self._client = genai.Client(
            api_key=config.gemini_api_key
        )

    def generate_json(
        self,
        prompt: str,
        response_schema: type[ResponseModel] = GeminiResponse,
    ) -> GeminiResult:
        """
        Ask Gemini for structured JSON and validate the result.

        No source files are modified here.
        """

        if not self.config.gemini_enabled:
            return GeminiResult(
                success=False,
                error="Gemini is disabled by configuration.",
            )

        if not self.config.gemini_api_key:
            return GeminiResult(
                success=False,
                error="GEMINI_API_KEY is not configured.",
            )

        if self._client is None:
            return GeminiResult(
                success=False,
                error="Gemini client is not initialized.",
            )

        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.config.gemini_model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                    },
                )

                raw_text = response.text

                if not raw_text:
                    return GeminiResult(
                        success=False,
                        error="Gemini returned an empty response.",
                    )

                parsed = json.loads(raw_text)
                validated = response_schema.model_validate(parsed)

                return GeminiResult(
                    success=True,
                    response=validated,
                )

            except json.JSONDecodeError as exc:
                return GeminiResult(
                    success=False,
                    error=f"Gemini returned invalid JSON: {exc}",
                )

            except ValidationError as exc:
                return GeminiResult(
                    success=False,
                    error=f"Gemini response failed validation: {exc}",
                )

            except Exception as exc:
                error_text = str(exc)

                is_temporary_unavailable = (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text
                )

                is_quota_exhausted = (
                    "429" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                )

                if (
                    is_temporary_unavailable
                    and not is_quota_exhausted
                    and attempt < max_attempts
                ):
                    time.sleep(2 ** attempt)
                    continue

                return GeminiResult(
                    success=False,
                    error=f"Gemini request failed: {exc}",
                )

        return GeminiResult(
            success=False,
            error="Gemini request failed after retry attempts.",
        )