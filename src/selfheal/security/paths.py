"""Path validation helpers: keep every file operation inside approved roots."""
from __future__ import annotations

import os
from pathlib import Path


def resolve_within(root: str | os.PathLike, path: str | os.PathLike) -> Path:
    """Resolve `path` (absolute, or relative to root) and require it inside root."""
    root_path = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved = candidate.resolve()
    if resolved != root_path and root_path not in resolved.parents:
        raise ValueError(f"Path escapes the project root: {path}")
    return resolved


def allowed_roots() -> list[Path]:
    """Roots MCP tools may touch: SELFHEAL_ALLOWED_ROOTS (os.pathsep list) or cwd."""
    raw = os.getenv("SELFHEAL_ALLOWED_ROOTS", "")
    roots = [Path(p).resolve() for p in raw.split(os.pathsep) if p.strip()]
    return roots or [Path.cwd().resolve()]


def ensure_allowed(path: str | os.PathLike) -> Path:
    resolved = Path(path).resolve()
    for root in allowed_roots():
        if resolved == root or root in resolved.parents:
            return resolved
    raise ValueError(f"Path is outside the allowed roots: {path}")
