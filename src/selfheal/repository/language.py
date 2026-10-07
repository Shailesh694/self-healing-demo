"""
Language detection + adapter capability registry.

Spec section 6: design a language-adapter architecture so additional
languages can be added without rewriting the engine, but never claim
support for a language that isn't actually implemented (spec rule #14).
Python is the only FULL adapter in this version; every other language is
detected (so it's visible and honest in scan output) but explicitly marked
UNSUPPORTED until its own phase implements it.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    C = "c"
    CPP = "cpp"
    GO = "go"
    JAVA = "java"
    RUST = "rust"
    UNKNOWN = "unknown"


class SupportLevel(str, Enum):
    """How much the engine can actually do for a given language.

    FULL: structural indexing, AST scoping, deterministic + AI remediation.
    PARTIAL: detected and indexed, but remediation is limited or unavailable.
    UNSUPPORTED: detected only. No indexing, no remediation — and the engine
    says so explicitly rather than silently doing nothing.
    """

    FULL = "full"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


_EXTENSION_MAP: Dict[str, Language] = {
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".c": Language.C,
    ".h": Language.C,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".go": Language.GO,
    ".java": Language.JAVA,
    ".rs": Language.RUST,
}

_SUPPORT_MAP: Dict[Language, SupportLevel] = {
    Language.PYTHON: SupportLevel.FULL,
    Language.JAVASCRIPT: SupportLevel.UNSUPPORTED,
    Language.TYPESCRIPT: SupportLevel.UNSUPPORTED,
    Language.C: SupportLevel.UNSUPPORTED,
    Language.CPP: SupportLevel.UNSUPPORTED,
    Language.GO: SupportLevel.UNSUPPORTED,
    Language.JAVA: SupportLevel.UNSUPPORTED,
    Language.RUST: SupportLevel.UNSUPPORTED,
    Language.UNKNOWN: SupportLevel.UNSUPPORTED,
}


def detect_language(path: Path) -> Language:
    """Detect language purely from file extension.

    Deliberately simple for this phase: extension mapping resolves the vast
    majority of real files. Content-sniffing (shebangs, etc.) can be added
    later if a real repository needs it — no point adding that complexity
    speculatively.
    """
    return _EXTENSION_MAP.get(path.suffix.lower(), Language.UNKNOWN)


def support_level(language: Language) -> SupportLevel:
    return _SUPPORT_MAP.get(language, SupportLevel.UNSUPPORTED)