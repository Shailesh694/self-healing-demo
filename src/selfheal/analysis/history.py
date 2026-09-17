from __future__ import annotations

import json
from pathlib import Path

from .report import RepairReport


def save_report(
    report: RepairReport,
    history_file: str = ".selfheal_history.json",
) -> None:
    path = Path(history_file)

    history: list[dict] = []

    if path.exists():
        try:
            history = json.loads(
                path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            history = []

    history.append(
        {
            "status": report.status,
            "file_path": report.file_path,
            "problem": report.problem,
            "confidence": report.confidence,
            "tests_passed": report.tests_passed,
            "message": report.message,
            "timestamp": report.timestamp,
        }
    )

    path.write_text(
        json.dumps(history, indent=2),
        encoding="utf-8",
    )


def load_history(
    history_file: str = ".selfheal_history.json",
) -> list[dict]:
    path = Path(history_file)

    if not path.exists():
        return []

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError:
        return []