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

        return cls(
            min_confidence=confidence,
            dry_run=dry_run,
            history_file=history_file,
        )