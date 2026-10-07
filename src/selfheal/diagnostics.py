from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DiagnosticResult:
    error_type: str
    message: str
    file_path: str | None = None
    line_number: int | None = None
    column: int | None = None


ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

FLAKE8_PATTERN = re.compile(
    r"^(?P<file>(?:[A-Za-z]:)?[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s+"
    r"(?P<code>[EWFC]\d{3})\s+(?P<msg>[^\r\n]*)\r?$",
    re.MULTILINE,
)

TRACEBACK_PATTERN = re.compile(
    r'File "([^"]+)", line (\d+)'
)


def diagnose(logs: str) -> DiagnosticResult:
    """
    Extract a conservative diagnostic signal from CI logs.

    Detects common Python exception types and, when present,
    extracts the source file and line number from traceback output.
    """

    if not logs.strip():
        return DiagnosticResult(
            error_type="unknown",
            message="No CI logs were provided",
        )

    logs = ANSI_PATTERN.sub("", logs)

    if not TRACEBACK_PATTERN.search(logs):
        flake = FLAKE8_PATTERN.search(logs)
        if flake:
            return DiagnosticResult(
                error_type=flake["code"],
                message=f"{flake['code']} {flake['msg']}".strip(),
                file_path=flake["file"].strip(),
                line_number=int(flake["line"]),
                column=int(flake["col"]),
            )

    lines = logs.splitlines()

    file_path: str | None = None
    line_number: int | None = None

    for line in lines:
        match = TRACEBACK_PATTERN.search(line)

        if match:
            file_path = match.group(1)
            line_number = int(match.group(2))

    for line in lines:
        if "SyntaxError" in line:
            return DiagnosticResult(
                error_type="SyntaxError",
                message=line.strip(),
                file_path=file_path,
                line_number=line_number,
            )

        if "NameError" in line:
            return DiagnosticResult(
                error_type="NameError",
                message=line.strip(),
                file_path=file_path,
                line_number=line_number,
            )

        if "TypeError" in line:
            return DiagnosticResult(
                error_type="TypeError",
                message=line.strip(),
                file_path=file_path,
                line_number=line_number,
            )

        if "ImportError" in line:
            return DiagnosticResult(
                error_type="ImportError",
                message=line.strip(),
                file_path=file_path,
                line_number=line_number,
            )

    return DiagnosticResult(
        error_type="unknown",
        message=lines[-1].strip(),
        file_path=file_path,
        line_number=line_number,
    )