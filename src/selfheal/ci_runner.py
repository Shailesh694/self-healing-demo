"""
CI entry point.

GitHub Actions runs `python heal.py`, which calls run_ci_remediation().
There is no separate healing implementation: every issue goes through the
same process_ci_failure() -> RemediationEngine path as the webhook and MCP
(candidate -> validation -> risk/policy -> sandbox -> regression ->
execution -> post-repair tests -> rollback on failure).

In CI the working tree is left modified (git_commit=False) so the pull
request action can open a PR for human review.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from .diagnostics import ANSI_PATTERN, FLAKE8_PATTERN, DiagnosticResult
from .policy import RepairPolicy
from .workflow import process_ci_failure


def parse_linter_issues(text: str) -> list[DiagnosticResult]:
    text = ANSI_PATTERN.sub("", text or "")
    issues = [
        DiagnosticResult(
            error_type=m["code"],
            message=f"{m['code']} {m['msg']}".strip(),
            file_path=m["file"].strip(),
            line_number=int(m["line"]),
            column=int(m["col"]),
        )
        for m in FLAKE8_PATTERN.finditer(text)
    ]
    # Bottom-up per file (and right-to-left within a line) so line and column
    # numbers of the remaining findings stay valid after each fix.
    issues.sort(key=lambda d: (d.file_path, -(d.line_number or 0), -(d.column or 0)))
    return issues


def has_vulnerabilities(text: str) -> bool:
    text = (text or "").strip()
    if not text or "No known vulnerabilities" in text:
        return False
    return any(marker in text for marker in ("PYSEC", "GHSA", "CVE-", "Vulnerab"))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _summarize(kind: str, diag: DiagnosticResult, out: dict) -> dict:
    return {
        "kind": kind,
        "file": diag.file_path,
        "line": diag.line_number,
        "code": diag.error_type,
        "status": out.get("status"),
        "reason": out.get("reason", ""),
        "patch_source": out.get("patch_source"),
    }


def run_ci_remediation(
    *,
    project_path: str = ".",
    linter_log: str = "linter_errors.log",
    cve_log: str = "cve_errors.log",
    git_commit: bool = False,
    ai_prepare=None,
    store=None,
) -> dict:
    root = Path(project_path)
    policy = RepairPolicy(allow_auto_apply=True)
    results: list[dict] = []

    def handle(kind: str, diag: DiagnosticResult) -> None:
        out = process_ci_failure(
            {"success": False, "logs": diag.message, "git_commit": git_commit},
            incident_id=f"ci-{uuid.uuid4().hex[:8]}",
            project_path=str(root),
            policy=policy,
            ai_prepare=ai_prepare,
            diagnostic=diag,
            store=store,
        )
        results.append(_summarize(kind, diag, out))

    for diag in parse_linter_issues(_read(root / linter_log)):
        handle("lint", diag)

    cve_text = _read(root / cve_log)
    if has_vulnerabilities(cve_text):
        handle(
            "dependency",
            DiagnosticResult(
                error_type="CVE", message=cve_text[:4000],
                file_path="requirements.txt", line_number=None,
            ),
        )

    return {
        "total": len(results),
        "repaired": sum(r["status"] == "repaired" for r in results),
        "results": results,
    }
