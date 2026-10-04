from pathlib import Path

from selfheal.git import GitRepository


def create_repo(path: Path) -> GitRepository:
    path.mkdir()

    repo = GitRepository(path)

    assert repo._run("init").success

    assert repo._run(
        "config",
        "user.email",
        "test@example.com",
    ).success

    assert repo._run(
        "config",
        "user.name",
        "SelfHeal Test",
    ).success

    file_path = path / "app.py"

    file_path.write_text(
        "print('old')\n",
        encoding="utf-8",
    )

    assert repo._run(
        "add",
        "app.py",
    ).success

    assert repo._run(
        "commit",
        "-m",
        "initial",
    ).success

    return repo


def test_full_git_remediation_lifecycle(
    tmp_path: Path,
):
    repo = create_repo(tmp_path / "repo")

    # 1. Create isolated healing branch.
    branch_result = repo.create_branch(
        "selfheal/fix-001"
    )

    assert branch_result.success is True

    branch = repo.current_branch()

    assert branch.success is True
    assert branch.stdout.strip() == (
        "selfheal/fix-001"
    )

    # 2. Apply candidate repair.
    patch = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-print('old')
+print('fixed')
"""

    patch_result = repo.apply_patch(patch)

    assert patch_result.success is True

    # 3. Verify candidate content.
    file_path = (
        tmp_path
        / "repo"
        / "app.py"
    )

    assert file_path.read_text(
        encoding="utf-8",
    ) == "print('fixed')\n"

    # 4. Verify Git sees the change.
    status = repo.status()

    assert status.success is True
    assert "app.py" in status.stdout

    # 5. Commit the verified candidate.
    commit_result = repo.prepare_commit(
        "selfheal: apply verified repair"
    )

    assert commit_result.success is True

    # 6. Working tree should now be clean.
    final_status = repo.status()

    assert final_status.success is True
    assert final_status.stdout.strip() == ""

    # 7. Verify the commit exists.
    log = repo._run(
        "log",
        "-1",
        "--pretty=%s",
    )

    assert log.success is True
    assert log.stdout.strip() == (
        "selfheal: apply verified repair"
    )