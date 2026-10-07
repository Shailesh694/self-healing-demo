import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAR = re.compile(r"\b(SELFHEAL_[A-Z_]+|GEMINI_API_KEY)\b")


def _code_text():
    files = list((ROOT / "src").rglob("*.py")) + [ROOT / "heal.py", ROOT / "scripts" / "demo.py",
                                                  ROOT / "scripts" / "smoke_live.py"]
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def test_documented_env_vars_are_read_by_the_code():
    code = _code_text()
    for doc in ("README.md", "RUN.md", ".env.example"):
        for var in set(VAR.findall((ROOT / doc).read_text(encoding="utf-8"))):
            assert var in code, f"{doc} documents {var} but no code reads it"


def test_requirements_cover_runtime_imports():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for dep in ("fastapi", "uvicorn", "pydantic", "mcp", "google-genai", "pyyaml", "pytest", "httpx"):
        assert dep in req, dep
    assert "requests" not in req and "flask" not in req
