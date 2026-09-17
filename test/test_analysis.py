from src.selfheal.analysis.diff import parse_diff
from src.selfheal.analysis.fix import create_candidate
from src.selfheal.analysis.validator import validate_candidate
from selfheal.analysis.policy import evaluate_policy
from selfheal.analysis.scorer import assess_risk


def test_parse_diff():
    diff = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 print("hello")
+print("world")
"""

    result = parse_diff(diff)

    assert len(result) == 1
    assert result[0].path == "app.py"
    assert result[0].additions == 1
    assert result[0].deletions == 0


def test_assess_risk_low():
    result = assess_risk(
        files_changed=1,
        lines_changed=1,
        changed_paths=["app.py"],
    )

    assert result.tier == "LOW"
    assert result.files_changed == 1
    assert result.lines_changed == 1
    assert result.security_sensitive is False


def test_assess_risk_medium():
    result = assess_risk(
        files_changed=2,
        lines_changed=10,
        changed_paths=["app.py", "utils.py"],
    )

    assert result.tier == "MEDIUM"


def test_assess_risk_high():
    result = assess_risk(
        files_changed=5,
        lines_changed=200,
        changed_paths=[
            "app.py",
            "utils.py",
            "service.py",
            "handler.py",
            "repair.py",
        ],
    )

    assert result.tier == "HIGH"


def test_assess_risk_critical():
    result = assess_risk(
        files_changed=1,
        lines_changed=1,
        changed_paths=[".env"],
    )

    assert result.tier == "CRITICAL"
    assert result.security_sensitive is True


def test_policy_low_allowed():
    risk = assess_risk(
        files_changed=1,
        lines_changed=1,
        changed_paths=["app.py"],
    )

    decision = evaluate_policy(risk)

    assert decision.allowed is True


def test_policy_high_requires_human():
    risk = assess_risk(
        files_changed=5,
        lines_changed=200,
        changed_paths=[
            "a.py",
            "b.py",
            "c.py",
            "d.py",
            "e.py",
        ],
    )

    decision = evaluate_policy(risk)

    assert decision.allowed is False


def test_create_candidate():
    candidate = create_candidate(
        file_path="app.py",
        description="Fix failing code",
        confidence=0.9,
        patch='print("fixed")',
    )

    assert candidate.file_path == "app.py"
    assert candidate.confidence == 0.9
    assert candidate.patch == 'print("fixed")'


def test_validate_candidate():
    patch = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("hello")
+print("fixed")
"""

    result = validate_candidate(
        file_path="app.py",
        confidence=0.9,
        patch=patch,
    )

    assert result.valid is True
    assert result.errors == []