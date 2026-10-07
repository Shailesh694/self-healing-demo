"""
CI entry point for GitHub Actions.

This is a thin wrapper around the SelfHeal engine in src/selfheal; it contains
no remediation logic of its own. It reads the scanner logs (flake8 and
pip-audit) and runs every finding through the same engine used by the
webhook and MCP.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from selfheal.ci_runner import run_ci_remediation  # noqa: E402


def main() -> int:
    if os.environ.get("GEMINI_API_KEY"):
        os.environ.setdefault("SELFHEAL_GEMINI_ENABLED", "true")
    summary = run_ci_remediation(project_path=".")
    print(json.dumps(summary, indent=2, default=str))
    return 0  # unfixed findings are reported, not fatal: the PR step reviews changes


if __name__ == "__main__":
    sys.exit(main())
