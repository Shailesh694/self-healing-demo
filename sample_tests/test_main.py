"""Verification target for the CI demo: the sample main.py that CI lints and repairs."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_main_prints_the_sum():
    result = subprocess.run(
        [sys.executable, "main.py"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "15"
