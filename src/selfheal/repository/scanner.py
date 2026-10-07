"""
Repository scanner.

Walks a repository and produces a flat, language-tagged file list. This is
deliberately metadata-only: it does not decide what's "relevant" to any
particular incident (that's the repository index in Phase 4, and the
context builder in Phase 6) and it does not parse file contents beyond a
cheap line count. Spec section 5 requires the engine to work on 1,000+ file
monorepos without choking, so this stays a single lightweight filesystem
pass with no parsing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from pydantic import BaseModel

from selfheal.repository.language import (
    Language,
    SupportLevel,
    detect_language,
    support_level,
)

DEFAULT_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
    ".idea",
    ".vscode",
}


class ScannedFile(BaseModel):
    """One file discovered by the scanner."""

    path: str  # relative to repo root, forward-slash separated
    language: Language
    support_level: SupportLevel
    size_bytes: int
    line_count: Optional[int] = None


def _is_ignored(relative_parts: Iterable[str], ignored_dirs: set) -> bool:
    return any(part in ignored_dirs for part in relative_parts)


def _count_lines(path: Path, max_bytes: int = 5_000_000) -> Optional[int]:
    """Count lines cheaply; skip very large or binary-looking files.

    Returns None rather than guessing for anything that isn't a normal
    small-to-medium text file — later phases (context builder) treat a
    missing line_count as "don't assume you know how big this is."
    """
    try:
        if path.stat().st_size > max_bytes:
            return None
        with path.open("rb") as f:
            chunk = f.read()
        if b"\x00" in chunk:  # crude binary check
            return None
        return chunk.count(b"\n") + (1 if chunk and not chunk.endswith(b"\n") else 0)
    except OSError:
        return None


def scan_repository(
    root: Path,
    extra_ignored_dirs: Optional[Iterable[str]] = None,
) -> List[ScannedFile]:
    """Walk `root` and return a ScannedFile for every non-ignored file.

    Raises FileNotFoundError if root doesn't exist, so a typo'd path fails
    loudly instead of silently returning an empty scan.
    """
    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository root does not exist: {root}")

    ignored_dirs = set(DEFAULT_IGNORED_DIRS)
    if extra_ignored_dirs:
        ignored_dirs.update(extra_ignored_dirs)

    results: List[ScannedFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _is_ignored(relative.parts, ignored_dirs):
            continue

        language = detect_language(path)
        results.append(
            ScannedFile(
                path=relative.as_posix(),
                language=language,
                support_level=support_level(language),
                size_bytes=path.stat().st_size,
                line_count=_count_lines(path),
            )
        )
    return results


def summarize_by_language(files: Iterable[ScannedFile]) -> dict:
    """Quick counts per language — used for CLI / logging output later."""
    counts: dict = {}
    for f in files:
        counts[f.language] = counts.get(f.language, 0) + 1
    return counts