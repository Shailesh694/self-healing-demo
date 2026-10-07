from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SelfHealConfig:
    min_confidence: float = 0.70

    test_command: tuple[str, ...] = (
        "python",
        "-m",
        "pytest",
    )

    dry_run: bool = True
    history_file: str = ".selfheal_history.json"

    # Gemini configuration
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: int = 60
    gemini_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "SelfHealConfig":
        confidence = float(
            os.getenv(
                "SELFHEAL_MIN_CONFIDENCE",
                "0.70",
            )
        )

        dry_run = os.getenv(
            "SELFHEAL_DRY_RUN",
            "true",
        ).lower() == "true"

        history_file = os.getenv(
            "SELFHEAL_HISTORY_FILE",
            ".selfheal_history.json",
        )

        gemini_api_key = os.getenv("GEMINI_API_KEY")

        gemini_model = os.getenv(
            "SELFHEAL_GEMINI_MODEL",
            "gemini-3.6-flash",
        )

        gemini_timeout_seconds = int(
            os.getenv(
                "SELFHEAL_GEMINI_TIMEOUT",
                "60",
            )
        )

        gemini_enabled = (
            os.getenv(
                "SELFHEAL_GEMINI_ENABLED",
                "false",
            ).lower()
            == "true"
        )

        return cls(
            min_confidence=confidence,
            dry_run=dry_run,
            history_file=history_file,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            gemini_timeout_seconds=gemini_timeout_seconds,
            gemini_enabled=gemini_enabled,
        )