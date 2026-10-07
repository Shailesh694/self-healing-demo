"""
Deterministic safety gate for whole-file AI rewrites.

The standalone CI script (heal.py) asks an LLM for a complete replacement of
main.py / requirements.txt. This gate checks that output with the same
deterministic risk model used by the engine before anything is written.
"""
from __future__ import annotations

import ast
import difflib
import json
import tomllib
import re
from dataclasses import dataclass, field

from .analysis.scorer import assess_risk

MAX_CHANGED_RATIO = 0.6
MIN_LINES_FOR_RATIO = 20  # ratio is meaningless for tiny files
ALLOWED_TIERS = {"LOW", "MEDIUM"}
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9_.\-]+)")


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def _changed_lines(old: str, new: str) -> int:
    return sum(
        1
        for line in difflib.unified_diff(
            old.splitlines(), new.splitlines(), lineterm="", n=0
        )
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    )


def _top_level_names(tree: ast.AST) -> set[str]:
    return {
        n.name
        for n in getattr(tree, "body", [])
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def check_python_rewrite(path: str, original: str, new: str) -> GateResult:
    reasons: list[str] = []
    if not new.strip():
        return GateResult(False, ["empty output"])

    try:
        new_tree = ast.parse(new)
    except SyntaxError as exc:
        return GateResult(False, [f"output is not valid Python: {exc.msg}"])

    try:
        removed = _top_level_names(ast.parse(original)) - _top_level_names(new_tree)
    except SyntaxError:
        removed = set()  # original already broken; nothing to preserve
    if removed:
        reasons.append(f"removed definitions: {sorted(removed)}")

    changed = _changed_lines(original, new)
    risk = assess_risk(files_changed=1, lines_changed=changed, changed_paths=[path])
    if risk.tier not in ALLOWED_TIERS:
        reasons.append(f"risk tier {risk.tier} not auto-appliable")
    total = len(original.splitlines())
    if total >= MIN_LINES_FOR_RATIO and changed / (2 * total) > MAX_CHANGED_RATIO:
        reasons.append("rewrite touches too much of the file")
    return GateResult(not reasons, reasons)


def _req_names(text: str) -> tuple[set[str], list[str]]:
    names, bad = set(), []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-") or "://" in line or "@" in line:
            bad.append(line)
            continue
        m = _REQ_NAME.match(line)
        if m:
            names.add(m.group(1).lower().replace("_", "-"))
    return names, bad


def check_requirements_rewrite(original: str, new: str) -> GateResult:
    if not new.strip():
        return GateResult(False, ["empty output"])
    old_names, _ = _req_names(original)
    new_names, bad = _req_names(new)
    reasons: list[str] = []
    if bad:
        reasons.append(f"unsafe requirement lines: {bad}")
    if new_names - old_names:
        reasons.append(f"new packages added: {sorted(new_names - old_names)}")
    if old_names - new_names:
        reasons.append(f"packages removed: {sorted(old_names - new_names)}")
    return GateResult(not reasons, reasons)



def check_rewrite(path: str, original: str, new: str) -> GateResult:
    """Format-aware gate. Unsupported file types are rejected (fail closed)."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""

    if ext == ".py":
        return check_python_rewrite(path, original, new)
    if name.startswith("requirements") and ext == ".txt":
        return check_requirements_rewrite(original, new)
    if ext == ".json":
        try:
            json.loads(new)
        except ValueError as exc:
            return GateResult(False, [f"invalid JSON: {exc}"])
        return GateResult(True)
    if ext == ".toml":
        try:
            tomllib.loads(new)
        except tomllib.TOMLDecodeError as exc:
            return GateResult(False, [f"invalid TOML: {exc}"])
        return GateResult(True)
    if ext in {".yml", ".yaml"}:
        try:
            import yaml
        except ImportError:
            return GateResult(False, ["YAML validation unavailable"])
        try:
            yaml.safe_load(new)
        except yaml.YAMLError as exc:
            return GateResult(False, [f"invalid YAML: {exc}"])
        return GateResult(True)
    return GateResult(False, [f"automatic rewrite not supported for '{ext or name}'"])
