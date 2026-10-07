"""Validation for commands that the engine/MCP will execute."""
from __future__ import annotations

import re
import sys
from pathlib import Path

_SAFE_ARG = re.compile(r"^[\w./\\:=,@+-]+$")
_FORBIDDEN_ARGS = {"-p", "-c", "--pyargs", "--confcutdir", "--import-mode"}


def default_test_command(target: str = ".") -> list[str]:
    return [sys.executable, "-m", "pytest", target, "-q"]


def validate_test_command(command: list[str]) -> list[str]:
    """Only `python -m pytest <safe args>` is allowed. Anything else is rejected."""
    if not isinstance(command, (list, tuple)) or not command:
        raise ValueError("command must be a non-empty list")
    if not all(isinstance(part, str) and part for part in command):
        raise ValueError("command parts must be non-empty strings")

    exe = Path(command[0]).stem.lower()
    allowed = {"python", "python3", "py", Path(sys.executable).stem.lower()}
    if exe not in allowed:
        raise ValueError(f"executable not allowed: {command[0]}")
    if list(command[1:3]) != ["-m", "pytest"]:
        raise ValueError("only 'python -m pytest ...' commands are allowed")

    for arg in command[3:]:
        if arg in _FORBIDDEN_ARGS or arg.startswith("-p"):
            raise ValueError(f"pytest argument not allowed: {arg}")
        if not _SAFE_ARG.match(arg):
            raise ValueError(f"unsafe pytest argument: {arg!r}")
    return list(command)
