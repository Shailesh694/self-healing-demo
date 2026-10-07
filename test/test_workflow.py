from src.selfheal.workflow import process_ci_failure


def test_successful_ci_is_ignored():
    result = process_ci_failure(
        {
            "success": True,
            "branch": "main",
            "commit": "abc123",
            "logs": "",
        },
        incident_id="INC-001",
    )

    assert result["status"] == "ignored"


def test_failed_ci_is_diagnosed():
    result = process_ci_failure(
        {
            "success": False,
            "branch": "main",
            "commit": "abc123",
            "logs": "NameError: name 'foo' is not defined",
        },
        incident_id="INC-002",
    )

    assert result["status"] == "diagnosed"
    assert result["diagnostic"].error_type == "NameError"

    risk = result["analysis"]["risk"]

    assert risk.tier == "LOW"
    assert risk.security_sensitive is False

def test_failed_ci_can_run_repair_pipeline(tmp_path):
    from src.selfheal.analysis.pipeline import run_repair_pipeline

    target = tmp_path / "app.py"
    target.write_text(
        'print("hello")\n',
        encoding="utf-8",
    )

    patch = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("hello")
+print("fixed")
"""

    result = run_repair_pipeline(
        file_path=str(target),
        problem="Application output is incorrect",
        confidence=0.9,
        patch=patch,
        dry_run=True,
    )

    assert result["status"] == "validated"
    assert result["dry_run"] is True
    assert result["applied"] is False
    assert result["candidate"].patch == patch
def test_repair_pipeline_applies_patch(tmp_path):
    from src.selfheal.analysis.pipeline import run_repair_pipeline

    target = tmp_path / "app.py"

    target.write_text(
        'print("hello")\n',
        encoding="utf-8",
    )

    patch = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print("hello")
+print("fixed")
"""

    result = run_repair_pipeline(
        file_path=str(target),
        problem="Application output is incorrect",
        confidence=0.95,
        patch=patch,
        dry_run=False,
    )

    assert result["status"] == "validated"
    assert result["dry_run"] is False
    assert result["applied"] is True

    assert target.read_text(encoding="utf-8") == 'print("fixed")\n'
def test_repair_and_verify_succeeds(tmp_path):
    from src.selfheal.analysis.repair import repair_and_verify

    target = tmp_path / "app.py"
    target.write_text(
        'def answer():\n'
        '    return 1\n',
        encoding="utf-8",
    )

    patch = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def answer():
-    return 1
+    return 2
"""

    test_file = tmp_path / "test_app.py"
    test_file.write_text(
        "from app import answer\n\n"
        "def test_answer():\n"
        "    assert answer() == 2\n",
        encoding="utf-8",
    )

    result = repair_and_verify(
        file_path=str(target),
        problem="answer() returns the wrong value",
        confidence=0.95,
        patch=patch,
        project_path=str(tmp_path),
    )

    assert result["status"] == "repaired"
    assert result["tests_passed"] is True
    assert "1 passed" in result["test_output"]
def test_repair_and_verify_rolls_back_on_test_failure(tmp_path):
    from src.selfheal.analysis.repair import repair_and_verify

    target = tmp_path / "app.py"

    original = (
        "def answer():\n"
        "    return 1\n"
    )

    target.write_text(
        original,
        encoding="utf-8",
    )

    patch = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def answer():
-    return 1
+    return 999
"""

    test_file = tmp_path / "test_app.py"
    test_file.write_text(
        "from app import answer\n\n"
        "def test_answer():\n"
        "    assert answer() == 1\n",
        encoding="utf-8",
    )

    result = repair_and_verify(
        file_path=str(target),
        problem="answer() returns the wrong value",
        confidence=0.95,
        patch=patch,
        project_path=str(tmp_path),
    )

    assert result["status"] == "rolled_back"
    assert result["tests_passed"] is False

    assert target.read_text(
        encoding="utf-8"
    ) == original
def test_diagnosis_extracts_file_and_line():
    from src.selfheal.diagnostics import diagnose

    logs = """\
Traceback (most recent call last):
  File "app.py", line 2, in <module>
    print(foo)
NameError: name 'foo' is not defined
"""

    result = diagnose(logs)

    assert result.error_type == "NameError"
    assert result.file_path == "app.py"
    assert result.line_number == 2
def test_repair_strategy_generates_nameerror_patch(tmp_path):
    from src.selfheal.analysis.repair_strategy import (
        generate_repair_patch,
    )

    target = tmp_path / "app.py"

    target.write_text(
        'print(foo)\n',
        encoding="utf-8",
    )

    patch = generate_repair_patch(
        file_path=str(target),
        error_type="NameError",
        message="NameError: name 'foo' is not defined",
        line_number=1,
    )

    assert patch is not None
    assert 'print(foo)' in patch
    assert 'print("fixed")' in patch
def test_repair_strategy_rejects_unsupported_nameerror(tmp_path):
    from src.selfheal.analysis.repair_strategy import (
        generate_repair_patch,
    )

    target = tmp_path / "app.py"

    target.write_text(
        "result = foo + 1\n",
        encoding="utf-8",
    )

    patch = generate_repair_patch(
        file_path=str(target),
        error_type="NameError",
        message="NameError: name 'foo' is not defined",
        line_number=1,
    )

    assert patch is None
def test_repair_strategy_patch_can_be_validated_and_applied(tmp_path):
    from src.selfheal.analysis.repair_strategy import (
        generate_repair_patch,
    )
    from src.selfheal.analysis.pipeline import (
        run_repair_pipeline,
    )

    target = tmp_path / "app.py"

    target.write_text(
        'print(foo)\n',
        encoding="utf-8",
    )

    patch = generate_repair_patch(
        file_path=str(target),
        error_type="NameError",
        message="NameError: name 'foo' is not defined",
        line_number=1,
    )

    assert patch is not None

    result = run_repair_pipeline(
        file_path=str(target),
        problem="NameError: name 'foo' is not defined",
        confidence=0.95,
        patch=patch,
        dry_run=False,
    )

    assert result["status"] == "validated"
    assert result["applied"] is True

    assert target.read_text(
        encoding="utf-8"
    ) == 'print("fixed")\n'
def test_workflow_auto_apply_repairs_and_verifies(tmp_path):
    from src.selfheal.policy import RepairPolicy

    target = tmp_path / "app.py"

    target.write_text(
        'print(foo)\n',
        encoding="utf-8",
    )

    test_file = tmp_path / "test_app.py"
    test_file.write_text(
        "def test_app_runs():\n"
        "    import app\n",
        encoding="utf-8",
    )

    logs = f'''\
Traceback (most recent call last):
  File "{target}", line 1, in <module>
    print(foo)
NameError: name 'foo' is not defined
'''

    result = process_ci_failure(
        {
            "success": False,
            "branch": "main",
            "commit": "demo123",
            "logs": logs,
        },
        incident_id="INC-AUTO-001",
        project_path=str(tmp_path),
        policy=RepairPolicy(
            allow_auto_apply=True,
        ),
    )

    assert result["status"] == "repaired"
    assert result["repair"]["status"] == "repaired"
    assert result["repair"]["tests_passed"] is True

    assert target.read_text(
        encoding="utf-8"
    ) == 'print("fixed")\n'
def test_workflow_default_policy_requires_review(tmp_path):
    target = tmp_path / "app.py"

    original = 'print(foo)\n'

    target.write_text(
        original,
        encoding="utf-8",
    )

    logs = f'''\
Traceback (most recent call last):
  File "{target}", line 1, in <module>
    print(foo)
NameError: name 'foo' is not defined
'''

    result = process_ci_failure(
        {
            "success": False,
            "branch": "main",
            "commit": "demo123",
            "logs": logs,
        },
        incident_id="INC-SAFE-001",
        project_path=str(tmp_path),
    )

    assert result["status"] == "diagnosed"
    assert result["analysis"]["decision"].action == "review"

    assert target.read_text(
        encoding="utf-8"
    ) == original